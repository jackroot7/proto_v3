from django.contrib import admin
from .models import StaffProfile, AttendanceRecord, DisciplinaryRecord
admin.site.register(StaffProfile)
admin.site.register(AttendanceRecord)
admin.site.register(DisciplinaryRecord)