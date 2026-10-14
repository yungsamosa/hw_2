"""
views.py — HTTP request handlers for AttendanceChimp.

Each view corresponds to one URL endpoint.  Views receive an HTTP request,
interact with the database via models.py, and return an HTTP response.
"""

from django.shortcuts import render, redirect
from django.http import (HttpResponse, HttpResponseForbidden,
                         HttpResponseBadRequest, JsonResponse)
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login
from datetime import datetime
import zoneinfo
import json
import io

# from .models import (InstructorProfile, StudentProfile, Course, Enrollment,
#                      Lecture, QRCodeUpload, is_instructor, is_student,
#                      getUploadsForCourse)

CDT = zoneinfo.ZoneInfo("America/Chicago")


# ---------------------------------------------------------------------------
# HW2  — index, time, sum
# ---------------------------------------------------------------------------

def index(request):
    """Render the home page (index.html)."""

    context = {}
    return render(request, 'app/index.html', context)

def time_view(request):
    """Returns a plaintext HttpResponse containing the current time in CST"""
    time = datetime.now(CDT)
    return HttpResponse(f"{time}")

def sum_view(request):
    """Reads query params and returns the sum"""
    try:
        n1 = request.GET['n1']
        n2 = request.GET['n2']
        return HttpResponse(int(n1) + int(n2))
    except (KeyError, ValueError):
        return HttpResponseBadRequest("n1 and n2 must be ints")


# ---------------------------------------------------------------------------
# HW4  — user creation
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# HW5  — courses, lectures, QR uploads, dump
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# HW6  — getUploads
# ---------------------------------------------------------------------------



