"""
models.py — Data model for AttendanceChimp.

AttendanceChimp is an electronic class attendance tool.  Instructors create
courses and lectures; each lecture is assigned a random QR code.  Students
photograph the QR code and upload the image.  The system decodes the QR code,
matches it to a lecture, and records the attendance.

Entities
--------
- InstructorProfile : extends Django User -> instructor-specific data
- StudentProfile    : extends Django User -> student-specific data
- Course            : a course taught by one instructor
- Enrollment        : junction table linking students to courses
- Lecture           : a single class meeting (has a QR-code identifier)
- QRCodeUpload      : a student's uploaded QR-code photograph

Relationships (from the ER diagram)
-----------------------------------
    InstructorProfile ||--o<  Course          "teaches"
    Course            ||--o<  Lecture         "meets as"
    Course            ||--o<  Enrollment      "includes"
    StudentProfile    ||--o<  Enrollment      "has"
    StudentProfile    ||--o<  QRCodeUpload    "submits"
    Lecture           o|--o<  QRCodeUpload    "validated against" (optional)

The ``name`` and ``email`` attributes shown on the two profile entities live on
the built-in ``auth_user`` row that each profile extends; they are exposed here
as read-only properties.
"""

from django.db import models
from django.contrib.auth.models import User

import logging
import string
import random

logger = logging.getLogger(__name__) # set up tracking, auditing, and debugging
                                                               # allows using logger.warning(), logger.error(), 
                                                               # logger.info(), etc. Better than print() for debuggin... 

QR_CODE_LENGTH = 12
QR_CODE_ALPHABET = string.ascii_uppercase + string.digits


def generate_qr_code(length=QR_CODE_LENGTH, max_attempts=10):
    """Return a random QR token that no existing Lecture is already using.

    Tokens are uppercase letters and digits, which survive the round trip
    through a printed and photographed QR code better than mixed-case strings.
    Collisions are retried; a broken random source raises ``RuntimeError``
    rather than silently reusing a code.
    """
    for _ in range(max_attempts):
        code = ''.join(random.choices(QR_CODE_ALPHABET, k=length))
        if not Lecture.objects.filter(qr_code=code).exists():
            return code
    logger.error("Could not generate a unique QR code in %d attempts", max_attempts)
    raise RuntimeError("Unable to generate a unique QR code")


# ---------------------------------------------------------------------------
# User profiles
# ---------------------------------------------------------------------------

class InstructorProfile(models.Model):
    """Instructor-specific data attached one-to-one to a Django ``User``.

    The ``user`` field doubles as the primary key, so ``instructor.id`` is the
    same integer as ``instructor.user.id`` -- the ``id PK`` of the ER diagram.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='instructor_profile',
    )

    def __str__(self):
        return f"Instructor: {self.name} <{self.email}>"

    @property
    def name(self):
        """Display name, falling back to the username when no name is set."""
        return self.user.get_full_name() or self.user.username

    @property
    def email(self):
        """The instructor's email address (stored on ``auth_user``)."""
        return self.user.email


class StudentProfile(models.Model):
    """Student-specific data attached one-to-one to a Django ``User``.

    Like :class:`InstructorProfile`, the one-to-one link is the primary key, so
    a single ``User`` maps to at most one student profile.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='student_profile',
    )

    def __str__(self):
        return f"Student: {self.name} <{self.email}>"

    @property
    def name(self):
        """Display name, falling back to the username when no name is set."""
        return self.user.get_full_name() or self.user.username

    @property
    def email(self):
        """The student's email address (stored on ``auth_user``)."""
        return self.user.email


# ---------------------------------------------------------------------------
# Course
# ---------------------------------------------------------------------------

class Course(models.Model):
    """A course taught by exactly one instructor.

    ``meeting_days`` and ``meeting_time`` describe the recurring schedule;
    individual meetings are stored as :class:`Lecture` rows.
    """

    name = models.CharField(max_length=200)
    instructor = models.ForeignKey(
        InstructorProfile,
        on_delete=models.CASCADE,
        related_name='courses',
    )
    meeting_days = models.CharField(
        max_length=7,
        blank=True,
        help_text="Weekday codes, one character each: M T W R F S U (e.g. 'MWF').",
    )
    meeting_time = models.TimeField(null=True, blank=True)

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Enrollment
# ---------------------------------------------------------------------------

class Enrollment(models.Model):
    """Junction row linking one student to one course.

    The ER diagram models this as its own entity (with its own ``id``) rather
    than a bare many-to-many, so it is declared explicitly.  The
    ``unique_together`` constraint keeps a student from being enrolled in the
    same course twice.
    """

    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name='enrollments',
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='enrollments',
    )

    class Meta:
        unique_together = [['student', 'course']]

    def __str__(self):
        return f"{self.student.name} in {self.course.name}"


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------

class Lecture(models.Model):
    """A single meeting of a course, identified by a unique QR token.

    The instructor displays ``qr_code`` as a QR image at the start of class;
    students photograph it and upload the photo, which is matched back to this
    row by looking the token up in ``qr_code``.
    """

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='lectures',
    )
    date = models.DateField()
    qr_code = models.CharField(
        max_length=64,
        unique=True,
        default=generate_qr_code,
    )

    def __str__(self):
        return f"{self.course.name} - {self.date}"


# ---------------------------------------------------------------------------
# QR Code Upload
# ---------------------------------------------------------------------------

class QRCodeUpload(models.Model):
    """A photograph of a QR code submitted by a student.

    ``lecture`` is nullable on purpose: the upload is stored first and matched
    second, so a photo whose code could not be decoded (or did not match any
    lecture) is kept with ``lecture = None`` as an audit trail.  If the matched
    lecture is later deleted the upload survives with a null link.
    """

    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name='uploads',
    )
    lecture = models.ForeignKey(
        Lecture,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploads',
    )
    image = models.FileField(upload_to='qr_uploads/%Y/%m/%d/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        target = self.lecture or "unmatched"
        return f"{self.student.name} -> {target} @ {self.uploaded_at:%Y-%m-%d %H:%M}"


# ---------------------------------------------------------------------------
# Helper / API functions
# ---------------------------------------------------------------------------

def is_instructor(user):
    """Return True if ``user`` is authenticated and has an InstructorProfile."""
    return (user is not None
            and user.is_authenticated
            and InstructorProfile.objects.filter(pk=user.pk).exists())


def is_student(user):
    """Return True if ``user`` is authenticated and has a StudentProfile."""
    return (user is not None
            and user.is_authenticated
            and StudentProfile.objects.filter(pk=user.pk).exists())


def getUploadsForCourse(course):
    """Return every QRCodeUpload matched to any lecture of ``course``.

    Ordered newest first, with student/lecture pre-fetched so that rendering a
    roster does not trigger a query per row.
    """
    return (QRCodeUpload.objects
            .filter(lecture__course=course)
            .select_related('student__user', 'lecture')
            .order_by('-uploaded_at'))
