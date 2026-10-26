from django.urls import path

from portal import views

urlpatterns = [
    path("", views.home),
    path("api/appointments/", views.appointments),
    path("api/appointments/<int:pk>/history/", views.history),
    path("api/appointments/<int:pk>/<str:action>/", views.appointment_action),
]
