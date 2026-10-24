from django.contrib import admin

'''
Generates a complete CRUD (Create, Read, Update, Delete) interface for a *superuser*.
If you log in to http://localhost:8000/admin/ with your *superuser account*, you will sections for 
registered classes (tables). Clicking on them would reveal the database content. 
Clicking "Add New" enables to add a new record. Etc. 
'''

from .models import (InstructorProfile, StudentProfile, Course, Enrollment, Lecture, QRCodeUpload)

admin.site.register(InstructorProfile)
admin.site.register(StudentProfile)
admin.site.register(Course)
admin.site.register(Enrollment)
admin.site.register(Lecture)
admin.site.register(QRCodeUpload)
