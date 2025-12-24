from django.db import models

class MasterBase(models.Model):
    sl_no = models.CharField(max_length=50, blank=True, null=True)
    viva_cktid = models.CharField(max_length=100, blank=True, null=True)
    customer_name = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=255, blank=True, null=True)
    pincode = models.CharField(max_length=20, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    nni_location = models.CharField(max_length=255, blank=True, null=True)

    status = models.CharField(max_length=100, blank=True, null=True)
    done_by = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.customer_name or 'Unknown'} - {self.city or ''}"


class L2Master(models.Model):
    VivaCKTID = models.CharField(max_length=100)
    CustomerName = models.CharField(max_length=255)
    Address = models.TextField()
    Pincode = models.CharField(max_length=10, null=True, blank=True)
  # <-- ADD THIS
    Location = models.CharField(max_length=255)
    State = models.CharField(max_length=100)
    BW = models.CharField(max_length=50)
    Media = models.CharField(max_length=50)
    BBName = models.CharField(max_length=255, blank=True, null=True)
    BBContact = models.CharField(max_length=255, blank=True, null=True)
    OTC = models.CharField(max_length=100)
    MRC = models.CharField(max_length=100)
