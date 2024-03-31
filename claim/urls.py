from django.urls import path
from . import views

urlpatterns = [
    path('print/', views.print, name='print'),
    path('claim/invoice/<claimCode>/<invoiceType>', views.print_invoice),
    # path('attach/', views.attach, name='attach')
]
