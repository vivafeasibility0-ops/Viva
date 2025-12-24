# views.py
import os
import io
import re
import pandas as pd
import numpy as np

from django.conf import settings
from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.db import transaction
from django.utils import timezone
from django.db.models import Q

from .forms import UploadFileForm
from .models import MasterBase, L2Master



# =============================
# CONFIG
# =============================
MASTER_FILE_NAME = "master_data.xlsx"
MASTER_FILE_PATH = os.path.join(settings.MEDIA_ROOT, MASTER_FILE_NAME)


# =============================
# UTILITIES
# =============================
def _read_dataframe_from_uploaded_file(uploaded_file):
    uploaded_file.seek(0)
    name = uploaded_file.name.lower()

    if name.endswith(".csv"):
        return pd.read_csv(uploaded_file, dtype=str)
    elif name.endswith((".xls", ".xlsx")):
        return pd.read_excel(uploaded_file, engine="openpyxl", dtype=str)
    else:
        raise ValueError("Unsupported file type")


def _normalize_headers(df):
    df = df.copy()
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.lower()
        .str.replace(r"[\.\-_]+", " ", regex=True)
        .str.replace(r"\s+", " ", regex=True)
    )
    return df


def _ensure_and_clean(df, cols):
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df = df.fillna("").astype(str)

    if "city" in cols:
        df["city"] = df["city"].str.strip().str.upper()
    if "state" in cols:
        df["state"] = df["state"].str.strip().str.upper()
    if "pincode" in cols:
        df["pincode"] = df["pincode"].str.replace(r"\D+", "", regex=True)

    return df


def _normalize_status(s):
    def f(x):
        x = str(x).lower().strip()
        if x in ("feasible", "f", "yes"):
            return "Feasible"
        if x in ("not feasible", "nf", "no"):
            return "Not Feasible"
        if "wip" in x:
            return "WIP"
        return ""
    return s.map(f)


def _load_master_for_simple_mode():
    # 1️⃣ Excel fallback
    if os.path.exists(MASTER_FILE_PATH):
        df = pd.read_excel(MASTER_FILE_PATH, dtype=str)
        df = _normalize_headers(df)
        return _ensure_and_clean(df, ["city", "pincode"])

    # 2️⃣ DB fallback
    qs = MasterBase.objects.values("city", "pincode")
    df = pd.DataFrame(list(qs))
    if df.empty:
        return df
    df = _normalize_headers(df)
    return _ensure_and_clean(df, ["city", "pincode"])


# =============================
# DASHBOARD
# =============================
def dashboard(request):
    return render(request, "dashboard.html", {
        "master_form": UploadFileForm(),
        "input_form": UploadFileForm(),
        "master_file_exists": os.path.exists(MASTER_FILE_PATH)
    })


# =============================
# MASTER UPLOAD
# =============================
@transaction.atomic
def upload_dashboard_master(request):
    if request.method != "POST":
        return redirect("dashboard")

    form = UploadFileForm(request.POST, request.FILES)
    if not form.is_valid():
        return redirect("dashboard")

    df = _read_dataframe_from_uploaded_file(request.FILES["file"])
    df = _normalize_headers(df).fillna("")

    # Save Excel for SIMPLE mode
    df.to_excel(MASTER_FILE_PATH, index=False)

    col_map = {
        "city": ["city", "location"],
        "state": ["state"],
        "pincode": ["pincode", "pin"],
        "status": ["status"],
        "done_by": ["done by", "prepared", "report from"],
    }

    matched = {}
    for field, patterns in col_map.items():
        for col in df.columns:
            clean = re.sub(r"[^a-z0-9 ]", "", col)
            if any(p in clean for p in patterns):
                matched[field] = col
                break

    MasterBase.objects.all().delete()

    records = []
    for _, row in df.iterrows():
        rec = {}
        for k, v in matched.items():
            rec[k] = str(row.get(v, "")).strip()
        records.append(MasterBase(**rec))
        

    MasterBase.objects.bulk_create(records, batch_size=3000)
    

    return render(request, "dashboard.html", {
        "message": f"Master uploaded ({len(records):,} rows)",
        "master_form": UploadFileForm(),
        "input_form": UploadFileForm(),
        "master_file_exists": True
    })

# =============================
# FEASIBILITY CHECK
# =============================
def check_feasibility(request):
    if request.method != "POST":
        return redirect("dashboard")

    mode = request.POST.get("mode", "advanced").lower()
    if mode not in ("simple", "advanced"):
        mode = "advanced"

    df_in = _read_dataframe_from_uploaded_file(request.FILES["file"])
    df_in = _normalize_headers(df_in)
    df_in = _ensure_and_clean(df_in, ["city", "state", "pincode"])

    if mode == "simple":
        df_master = _load_master_for_simple_mode()
        if df_master.empty:
            return redirect("dashboard")

        df_master = df_master.drop_duplicates(["city", "pincode"])
        df_master["key"] = df_master["city"] + "_" + df_master["pincode"]
        df_in["key"] = df_in["city"] + "_" + df_in["pincode"]

        merged = df_in.merge(df_master[["key"]], on="key", how="left", indicator=True)
        merged["Status"] = np.where(merged["_merge"] == "both", "Feasible", "Not Feasible")
        final = merged.drop(columns=["key", "_merge"])

    else:
        df_master = pd.DataFrame.from_records(
            MasterBase.objects.values()
        )
        if df_master.empty:
            return redirect("dashboard")

        df_master = _normalize_headers(df_master)
        df_master = _ensure_and_clean(df_master, ["city", "state", "pincode"])

        m1 = df_master.drop_duplicates(["city", "state", "pincode"])
        m2 = df_master.drop_duplicates(["city", "pincode"])

        l1 = df_in.merge(m1, on=["city", "state", "pincode"], how="left", suffixes=("", "_l1"))
        l2 = df_in.merge(m2, on=["city", "pincode"], how="left", suffixes=("", "_l2"))

        s1 = _normalize_status(l1["status"])
        s2 = _normalize_status(l2["status"])

        final = df_in.copy()
        final["FinalStatus"] = np.where(
            s1 != "", s1,
            np.where(s2 != "", s2, "No Match Found")
        )

    # =============================
    # EXPORT EXCEL
    # =============================
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        final.to_excel(writer, index=False, sheet_name="Result")

    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    ts = timezone.now().strftime("%Y%m%d_%H%M%S")
    response["Content-Disposition"] = f'attachment; filename="Feasibility_{mode}_{ts}.xlsx"'
    return response


# =============================
# L2 SEARCH
# =============================
def l2_search_page(request):
    return render(request, "l2_search.html")


def upload_l2_master(request):
    if request.method == "POST":
        df = pd.read_excel(request.FILES["master_file"])
        L2Master.objects.all().delete()

        for _, r in df.iterrows():
            L2Master.objects.create(
                VivaCKTID=r.get("VivaCKTID", ""),
                CustomerName=r.get("Customer Name", ""),
                Address=r.get("Address", ""),
                Pincode=str(r.get("Pincode", "")),
                Location=r.get("Location", ""),
                State=r.get("State", ""),
                BW=str(r.get("BW", "")),
                Media=r.get("Media", ""),
                BBName=r.get("BBName", ""),
                BBContact=r.get("BBContact", ""),
                OTC=str(r.get("OTC", "")),
                MRC=str(r.get("MRC", "")),
            )
    
    return render(request, "l2_search.html", {"message": "L2 Master uploaded"})


def l2_search_api(request):
    q = request.GET.get("q", "")
    rows = L2Master.objects.filter(
        Q(VivaCKTID__icontains=q) |
        Q(Pincode__icontains=q) |
        Q(Location__icontains=q) |
        Q(State__icontains=q) |
        Q(CustomerName__icontains=q) |
        Q(BBName__icontains=q)

    )[:200]

    return JsonResponse({"data": list(rows.values())})
