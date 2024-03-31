import base64
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes
from location.models import LocationManager
from report.services import ReportService
# from core.security import checkUserWithRights
from .services import ClaimReportService
from .reports import claim
from .apps import ClaimConfig
from .models import ClaimAttachment
from django.utils.translation import gettext as _
import core
from rest_framework import status


@api_view(['GET'])
def print(request):
    if not request.user.has_perms(ClaimConfig.claim_print_perms):
        raise PermissionDenied(_("unauthorized"))
    report_service = ReportService(request.user)
    report_data_service = ClaimReportService(request.user)
    data = report_data_service.fetch(request.GET['uuid'])
    return report_service.process('claim_claim', data, claim.template)


import decimal    
def num2words(num):
    num = decimal.Decimal(num)
    decimal_part = num - int(num)
    num = int(num)

    # if decimal_part:
    #     return num2words(num) + " and  " + (" ".join(num2words(i) for i in str(decimal_part)[2:]))

    under_20 = ['Zero', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen', 'Seventeen', 'Eighteen', 'Nineteen']
    tens = ['Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety']
    above_100 = {100: 'Hundred', 1000: 'Thousand', 100000: 'Lakhs', 10000000: 'Crores'}

    if num < 20:
        return under_20[num]

    if num < 100:
        return tens[num // 10 - 2] + ('' if num % 10 == 0 else ' ' + under_20[num % 10])

    # find the appropriate pivot - 'Million' in 3,603,550, or 'Thousand' in 603,550
    pivot = max([key for key in above_100.keys() if key <= num])

    return num2words(num // pivot) + ' ' + above_100[pivot] + ('' if num % pivot==0 else ' ' + num2words(num % pivot))


# @api_view(["GET", "POST"])
# @permission_classes(
#     [
#         checkUserWithRights(
#             ClaimConfig.gql_query_claims_perms,
#         )
#     ]
# )
# def attach(request):
#     queryset = ClaimAttachment.objects.filter(*core.filter_validity())
#     if settings.ROW_SECURITY:
#         from location.models import LocationManager
#         queryset = LocationManager().build_user_location_filter_query(request.user._u, prefix='health_facility__location',
#                                                                       queryset=queryset.select_related("claim"), loc_types=['D'])
#     attachment = queryset\
#         .filter(id=request.GET['id'])\
#         .first()
#     if not attachment:
#         raise PermissionDenied(_("unauthorized"))

#     if ClaimConfig.claim_attachments_root_path and attachment.url is None:
#         response = HttpResponse(status=404)
#         return response

#     if not ClaimConfig.claim_attachments_root_path and attachment.document is None:
#         response = HttpResponse(status=404)
#         return response

#     response = HttpResponse(content_type=("application/x-binary" if attachment.mime is None else attachment.mime))
#     response['Content-Disposition'] = 'attachment; filename=%s' % attachment.filename
#     if ClaimConfig.claim_attachments_root_path:
#         f = open('%s/%s' % (ClaimConfig.claim_attachments_root_path, attachment.url), "rb")
#         response.write(f.read())
#         f.close()
#     else:
#         response.write(base64.b64decode(attachment.document))
#     return response
from io import BytesIO
from django.http import HttpResponse
from django.template.loader import get_template

from xhtml2pdf import pisa
from .models import Claim
def render_to_pdf(template_src, context_dict={}):
    template = get_template(template_src)
    html  = template.render(context_dict)
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("utf8")), result)
    if not pdf.err:
        return HttpResponse(result.getvalue(), content_type='application/pdf')
    return None

def print_invoice(request,claimCode,invoiceType):
    # try:
    # 1 = Customer Copy 2 = final copy
    if True and (invoiceType == '1' or invoiceType == '2'):
        claim = Claim.objects\
            .select_related('insuree','health_facility','refer_from','refer_to')\
            .filter(uuid = claimCode).first()
        if True and claim:
            # if invoiceType == '2' and claim.payment_status == Claim.PAYMENT_REJECTED and claim.status == Claim.PAYMENT_REJECTED:
            #     return HttpResponse('Claim Payment has been rejected')
            # elif invoiceType == '2' and claim.status != Claim.STATUS_VALUATED:
            #     return HttpResponse('Claim should be in Valuated state for final Invoice')
            # elif invoiceType == '2' and claim.payment_status != 2:
            #     return HttpResponse('Claim should be in Payment status should be in Paid state for final Invoice')
            
            item_total = 0
            service_total = 0
            #Customer Copy
            item_total = sum([item.price_asked * item.qty_provided for item in claim.items.all()])
            service_total = sum([item.price_asked * item.qty_provided for item in claim.services.all()])
            
            total = round(item_total + service_total,2)
            ssf_liability = round(0.8 * float(total),2)
            contributor_liability = round(0.2 * float(total),2)
            #In case of  Final
            unapproveAmount = 0

            if True: #oclaim.product_id == 1:
                 total_inword =num2words(claim.claimed)
            else:
                 total_inword =num2words(contributor_liability)
            context = {
                'claim':claim,
                'item_total':item_total,
                'service_total':service_total,
                'total':total,
                'ssf_liability':ssf_liability,
                'contributor_liability':contributor_liability,
                'total_inword':total_inword,
                'invoice_type':'Customer Copy' if invoiceType == '1' else 'Final Copy',
                'invoice_type_int':invoiceType,
                'unapproveAmount': unapproveAmount
            }
            pdf = render_to_pdf('invoice.html', context)
            return HttpResponse(pdf, content_type='application/pdf')
            # return render(request, 'final_invoice.html',context)
        else:
            return HttpResponse(status=404)
    else:
        return HttpResponse('Invalid invoice Type',status=status.HTTP_400_BAD_REQUEST)
