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

# Single-letter codes used in Course.meeting_days, indexed by Python's
# date.weekday() (Monday == 0).
WEEKDAY_CODES = ['M', 'T', 'W', 'R', 'F', 'S', 'U']


def generate_qr_code(length=QR_CODE_LENGTH):
    """Return a random, URL-safe token to embed in a lecture's QR code.

    The token is drawn from uppercase letters and digits, which survive the
    round trip through a printed/photographed QR code far better than
    mixed-case strings do.  Uniqueness is enforced by ``Lecture.qr_code``;
    callers that need a guaranteed-free value should use
    :func:`generate_unique_qr_code` instead.
    """
    return ''.join(random.choices(QR_CODE_ALPHABET, k=length))


def generate_unique_qr_code(length=QR_CODE_LENGTH, max_attempts=10):
    """Return a QR token that is not yet used by any existing Lecture.

    Retries on the (astronomically unlikely) collision and raises
    ``RuntimeError`` if it cannot find a free token, so that a broken random
    source fails loudly instead of silently reusing a code.
    """
    for _ in range(max_attempts):
        code = generate_qr_code(length)
        if not Lecture.objects.filter(qr_code=code).exists():
            return code
    logger.error("Could not generate a unique QR code in %d attempts", max_attempts)
    raise RuntimeError("Unable to generate a unique QR code")


# ---------------------------------------------------------------------------
# User profiles
# ---------------------------------------------------------------------------

class InstructorProfile(models.Model):
    """Instructor-specific data attached one-to-one to a Django ``User``.

    The ``user`` field doubles as the primary key so ``instructor.id`` is the
    same integer as ``instructor.user.id``. 
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='instructor_profile',
        help_text="The auth_user row this instructor profile extends.",
    )

    class Meta:
        verbose_name = "instructor profile"
        ordering = ['user__last_name', 'user__first_name']

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

    def teaches(self, course):
        """Return True if this instructor is the owner of ``course``."""
        return course.instructor_id == self.pk

    def create_course(self, name, meeting_days='', meeting_time=None):
        """Create and return a new Course taught by this instructor."""
        course = Course.objects.create(
            name=name,
            instructor=self,
            meeting_days=meeting_days,
            meeting_time=meeting_time,
        )
        logger.info("Instructor %s created course %s", self.pk, course.pk)
        return course


class StudentProfile(models.Model):
    """Student-specific data attached one-to-one to a Django ``User``.

    One-to-one link is the primary key, so a single ``User`` maps to at most one student profile.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='student_profile',
        help_text="The auth_user row this student profile extends.",
    )

    class Meta:
        verbose_name = "student profile"
        ordering = ['user__last_name', 'user__first_name']

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

    @property
    def courses(self):
        """QuerySet of every Course this student is enrolled in."""
        return Course.objects.filter(enrollments__student=self)

    def is_enrolled_in(self, course):
        """Return True if an Enrollment links this student to ``course``."""
        return Enrollment.objects.filter(student=self, course=course).exists()

    def enroll_in(self, course):
        """Enroll this student in ``course``; returns ``(enrollment, created)``.
        """
        enrollment, created = Enrollment.objects.get_or_create(
            student=self, course=course
        )
        if created:
            logger.info("Student %s enrolled in course %s", self.pk, course.pk)
        return enrollment, created

    def attended(self, lecture):
        """Return True if this student has a validated upload for ``lecture``."""
        return QRCodeUpload.objects.filter(student=self, lecture=lecture).exists()


# ---------------------------------------------------------------------------
# Course
# ---------------------------------------------------------------------------

class Course(models.Model):
    """A course taught by exactly one instructor.

    ``meeting_days`` is a string of weekday codes like "MWF", "TR" and
    ``meeting_time`` is the time of day the class starts. Individual meetings are stored as :class:`Lecture` rows.
    """

    name = models.CharField(
        max_length=200,
        help_text="Human-readable course title, e.g. 'Intro to Web Development'.",
    )
    instructor = models.ForeignKey(
        InstructorProfile,
        on_delete=models.CASCADE,
        related_name='courses',
        help_text="The single instructor who teaches this course.",
    )
    meeting_days = models.CharField(
        max_length=7,
        blank=True,
        help_text="Weekday codes, one character each: M T W R F S U (e.g. 'MWF').",
    )
    meeting_time = models.TimeField(
        null=True,
        blank=True,
        help_text="Local start time of each meeting.",
    )

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def meets_on(self, day):
        """Return True if ``day`` (a ``date``) falls on a scheduled weekday."""
        return WEEKDAY_CODES[day.weekday()] in self.meeting_days.upper()

    def students(self):
        """QuerySet of the StudentProfiles enrolled in this course."""
        return StudentProfile.objects.filter(enrollments__course=self)

    def enrollment_count(self):
        """Number of students currently enrolled."""
        return self.enrollments.count()

    def create_lecture(self, date, qr_code=None):
        """Create a Lecture for ``date`` with a freshly generated QR code.

        Pass ``qr_code`` only when reproducing a known token, otherwise a unique one is generated automatically.
        """
        lecture = Lecture.objects.create(
            course=self,
            date=date,
            qr_code=qr_code or generate_unique_qr_code(),
        )
        logger.info("Course %s created lecture %s for %s", self.pk, lecture.pk, date)
        return lecture


# ---------------------------------------------------------------------------
# Enrollment
# ---------------------------------------------------------------------------

class Enrollment(models.Model):
    """Junction row linking one student to one course.
    """

    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name='enrollments',
        help_text="The enrolled student.",
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='enrollments',
        help_text="The course the student is enrolled in.",
    )

    class Meta:
        unique_together = [['student', 'course']]
        ordering = ['course__name', 'student__user__last_name']

    def __str__(self):
        return f"{self.student.name} in {self.course.name}"


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------

class Lecture(models.Model):
    """A single meeting of a course, identified by a unique QR token. QR code picture is matched back to this
    row by :func:`record_qr_upload`.
    """

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='lectures',
        help_text="The course this lecture is a meeting of.",
    )
    date = models.DateField(
        help_text="Calendar date on which this lecture met.",
    )
    qr_code = models.CharField(
        max_length=64,
        unique=True,
        default=generate_qr_code,
        help_text="Random token encoded in this lecture's QR image. Unique.",
    )

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.course.name} - {self.date}"

    def attendees(self):
        """QuerySet of StudentProfiles with an upload validated against this lecture."""
        return StudentProfile.objects.filter(uploads__lecture=self).distinct()

    def attendance_count(self):
        """Number of distinct students recorded as present."""
        return self.attendees().count()

    def absentees(self):
        """QuerySet of enrolled students with no upload for this lecture."""
        return self.course.students().exclude(uploads__lecture=self)

    def regenerate_qr_code(self):
        """Issue a new token for this lecture, invalidating the old QR image."""
        self.qr_code = generate_unique_qr_code()
        self.save(update_fields=['qr_code'])
        logger.info("Regenerated QR code for lecture %s", self.pk)
        return self.qr_code


# ---------------------------------------------------------------------------
# QR Code Upload
# ---------------------------------------------------------------------------

class QRCodeUpload(models.Model):
    """Stores a photograph of a QR code submitted by a student.
    """

    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name='uploads',
        help_text="The student who submitted this image.",
    )
    lecture = models.ForeignKey(
        Lecture,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploads',
        help_text="Lecture this upload was validated against; null if unmatched.",
    )
    image = models.FileField(
        upload_to='qr_uploads/%Y/%m/%d/',
        help_text="The uploaded photograph of the QR code.",
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Server timestamp of the upload.",
    )

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        target = self.lecture or "unmatched"
        return f"{self.student.name} -> {target} @ {self.uploaded_at:%Y-%m-%d %H:%M}"

    @property
    def is_validated(self):
        """True once this upload has been matched to a lecture."""
        return self.lecture_id is not None

    def validate_against(self, qr_code):
        """Attach this upload to the Lecture whose token is ``qr_code``.

        Returns the matched :class:`Lecture`, or ``None`` if no lecture carries
        that token (in which case the upload is left unmatched).
        """
        lecture = Lecture.objects.filter(qr_code=qr_code).first()
        if lecture is None:
            logger.warning("Upload %s: no lecture for code %r", self.pk, qr_code)
            return None
        self.lecture = lecture
        self.save(update_fields=['lecture'])
        return lecture


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


def get_profile(user):
    """Return the InstructorProfile or StudentProfile for ``user``, else None.
    """
    if user is None or not user.is_authenticated:
        return None
    profile = InstructorProfile.objects.filter(pk=user.pk).first()
    return profile or StudentProfile.objects.filter(pk=user.pk).first()


def create_instructor(username, password, email='', first_name='', last_name=''):
    """Create a ``User`` plus its InstructorProfile and return the profile."""
    user = User.objects.create_user(
        username=username, password=password, email=email,
        first_name=first_name, last_name=last_name,
    )
    logger.info("Created instructor account %s", username)
    return InstructorProfile.objects.create(user=user)


def create_student(username, password, email='', first_name='', last_name=''):
    """Create a ``User`` plus its StudentProfile and return the profile."""
    user = User.objects.create_user(
        username=username, password=password, email=email,
        first_name=first_name, last_name=last_name,
    )
    logger.info("Created student account %s", username)
    return StudentProfile.objects.create(user=user)


def record_qr_upload(student, image, qr_code=None):
    """Store an uploaded QR photo and, if possible, match it to a lecture.
    """
    upload = QRCodeUpload.objects.create(student=student, image=image)
    lecture = upload.validate_against(qr_code) if qr_code else None
    return upload, lecture


def getUploadsForCourse(course):
    """Return every QRCodeUpload matched to any lecture of ``course``.
    """
    return (QRCodeUpload.objects
            .filter(lecture__course=course)
            .select_related('student__user', 'lecture')
            .order_by('-uploaded_at'))


def getUploadsForStudent(student, course=None):
    """Return a student's uploads, optionally narrowed to one ``course``."""
    uploads = QRCodeUpload.objects.filter(student=student)
    if course is not None:
        uploads = uploads.filter(lecture__course=course)
    return uploads.select_related('lecture__course').order_by('-uploaded_at')
