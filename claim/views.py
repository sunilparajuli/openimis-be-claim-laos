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








import io
from django.db import connection
import xlsxwriter



def query_to_excel_download_helper(query, custom_header=None, filename=None):
    output = io.BytesIO()
    cursor = connection.cursor()
    cursor.execute(query)

    header = [row[0] for row in cursor.description]
    if custom_header:
        header = custom_header
    rows = cursor.fetchall()
    # Create an new Excel file and add a worksheet.
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet("Report")

    # Create style for cells
    header_cell_format = workbook.add_format(
        {"bold": True, "border": True, "bg_color": "yellow"}
    )
    body_cell_format = workbook.add_format({"border": True})

    # header, rows = fetch_table_data(table_name)

    row_index = 0
    column_index = 0
    # if not custom_header:
    for column_name in header:
        # print('col_name', column_name)
        worksheet.write(row_index, column_index, column_name, header_cell_format)
        column_index += 1

    row_index += 1
    for row in rows:
        column_index = 0
        for column in row:
            worksheet.write(row_index, column_index, column, body_cell_format)
            column_index += 1
        row_index += 1

    # Closing workbook
    workbook.close()
    output.seek(0)
    response = HttpResponse(
        output.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="report_data.xlsx"'
    print("response", response)
    output.close()
    return response


@api_view(["GET"])
def ClaimToExcelExport(request):
    print("request", request.GET)

    # Extracting all parameters from the URL
    parent_location_params = [
        value
        for key, value in request.GET.items()
        if key.startswith("parent_location_")
    ]
    chfid = request.GET.get("chfid")
    last_name = request.GET.get("last_name")
    given_name = request.GET.get("given_name")
    gender = request.GET.get("gender")
    """
    # Initialize a queryset with all Insuree objects
    insuree_queryset = Insuree.objects.all()

    # Apply filters based on parameters
    if parent_location_params:
        # Filter based on parent locations
        for index, location_id in enumerate(parent_location_params):
            print("locationid", location_id)
            _location = Location.objects.filter(uuid=location_id).first()
            print("_location", _location)
            insuree_queryset = insuree_queryset.filter(family__location__id=_location.id)

    if chfid:
        # Filter based on chfid
        insuree_queryset = insuree_queryset.filter(chf_id=chfid)

    if last_name:
        # Filter based on last_name
        insuree_queryset = insuree_queryset.filter(last_name=last_name)

    if given_name:
        # Filter based on given_name
        insuree_queryset = insuree_queryset.filter(other_names=given_name)

    if gender:
        # Filter based on gender
        insuree_queryset = insuree_queryset.filter(gender=gender)

    queryset_string = str(insuree_queryset.query)
    print("query", insuree_queryset.query)
    """

    # Assuming `parent_location_params` is a list of UUID strings
    parent_location_filters = " OR ".join(
        [
            f'("tblLocations"."LocationUUID" = \'{location_id}\')'
            for location_id in parent_location_params
        ]
    )

    # Assuming `chfid`, `last_name`, `given_name`, and `gender` are provided as string values
    chfid_filter = f'("tblInsuree"."CHFID" = \'{chfid}\')' if chfid else ""
    last_name_filter = (
        f'("tblInsuree"."LastName" = \'{last_name}\')' if last_name else ""
    )
    given_name_filter = (
        f'("tblInsuree"."OtherNames" = \'{given_name}\')' if given_name else ""
    )
    gender_filter = f'("tblInsuree"."Gender" = \'{gender}\')' if gender else ""

    # Concatenate all filters
    filters = [
        filter
        for filter in [
            parent_location_filters,
            chfid_filter,
            last_name_filter,
            given_name_filter,
            gender_filter,
        ]
        if filter
    ]
    where_clause = " AND ".join(filters) if filters else "1=1"

    # Construct the SQL query
    sql_query = f"""
        SELECT 
            "tblInsuree"."CHFID",
            "tblInsuree"."LastName",
            "tblInsuree"."OtherNames", 
            "tblInsuree"."Gender", 
            "tblInsuree"."Email", 
            "tblInsuree"."Phone", 
            CAST("tblInsuree"."DOB" AS DATE),
            "tblInsuree"."status"
        FROM 
            "tblInsuree"
        INNER JOIN 
            "tblFamilies" ON "tblInsuree"."FamilyID" = "tblFamilies"."FamilyID"
        INNER JOIN 
            "tblLocations" ON "tblFamilies"."LocationId" = "tblLocations"."LocationId"
        WHERE 
            {where_clause} 
            AND "tblInsuree"."ValidityTo" IS NULL;
    """

    print(sql_query)
    if not request.user:
        raise PermissionDenied(_("unauthorized"))
    query_string = f"""
                     {sql_query}
                   """
    return query_to_excel_download_helper(query_string)
    # print('request.get', request.GET)
    print("request user", request.user.i_user.health_facility_id)

    hf_id = request.GET.get("hf_id", None)
    print("hf_id", hf_id)
    if hf_id:
        healthfacility_id = HealthFacility.objects.filter(code=hf_id).first().pk
    else:
        healthfacility_id = None
    print("healthfacility_id", healthfacility_id)
    if not hf_id:
        print("request.get", request.GET)
        health_facility_id = request.user.i_user.health_facility_id
        if request.user.i_user.health_facility_id:
            hf_id = HealthFacility.objects.filter(pk=health_facility_id).first().code
    claim_status = request.GET.get("claim_status")
    insuree_chfid = request.GET.get("chfid", None)
    fromDate = request.GET.get("from_date", "")  # datetime.now().strftime('%Y-%m-%d'))
    todate = request.GET.get("to_date", "")  # datetime.now().strftime('%Y-%m-%d'))
    claim_no = request.GET.get("claim_no")
    payment_status = request.GET.get("payment_status")
    product_code = request.GET.get("product")
    if product_code == "SSF0001":
        product_id = 2
    elif product_code == "SSF0002":
        product_id = 1
    else:
        product_id = None

    """
    # print(req_data['to_data'])
    response = HttpResponse(content_type='application/ms-excel')
    response['Content-Disposition'] = 'attachment; filename="claim_payment_status.xls"'

    wb = xlwt.Workbook(encoding='utf-8')
    ws = wb.add_sheet('Claims Payment Status')

    # Sheet header, first row
    row_num = 0

    font_style = xlwt.XFStyle()
    font_style.font.bold = True
    headers = ['Report Date',datetime.now().strftime('%Y-%m-%d'),'From Date',fromDate,'To Date',todate]
    for col_num in range(len(headers)):
        ws.write(row_num, col_num, headers[col_num], font_style)
    row_num+=1
    columns = ['Code','Insuree SSID','Insuree Name','Scheme Name','Sub Scheme','Claim Date', 'Claimed', 'Approved', 'Claim Status','Payment Status','Action Date','Payment Remarks' ]

    for col_num in range(len(columns)):
        ws.write(row_num, col_num, columns[col_num], font_style)

    # Sheet body, remaining rows
    font_style = xlwt.XFStyle()
    statuses = {
                1: "Rejected",
                2: "Entered",
                4: "Checked",
                6: "Recommended",
                8: "Processed",
                9: "Forwarded",
                16: "Valuated",
            }
    payment_statuses = {
                0: "Booked",
                1: "Rejected",
                2: "Paid",
            }
    # a = useDict.get(useBy,None)
    hf = HealthFacility.objects.all().filter(code = hf_id,validity_to = None).first()
    rows = Claim.objects\
        .select_related('product','subProduct','insuree')\
        .filter(health_facility=hf,date_claimed__gte = fromDate,date_claimed__lte=todate,validity_to=None)\
        .order_by('date_claimed')
    # print('query',rows.query)
    if insuree_no:
        insuree = Insureee.objects.filter(chf_id=insuree_no,validity_to=None).first() 
        rows = rows.filter(insuree= insuree)
    l = []
    """
    try:
        # print('queries',rows.query)
        from .query_string_report import construct_query_string

        columns = [
            "Code",
            "Insuree SSID",
            "Insuree Name",
            "Scheme Name",
            "Sub Scheme",
            "Claim Date",
            "Claimed",
            "Approved",
            "Claim Status",
            "Payment Status",
            "Action Date",
            "Payment Remarks",
        ]

        query_string = f""" 
              SELECT 
              tblclaim.ClaimCode, 
              CONCAT(
                tblinsuree.OtherNames, ' ', tblInsuree.LastName
              ) as Insuree, 
              tblInsuree.CHFID,
              CONCAT(tblclaim.DateClaimed, '.') as DateClaimed, 
              tblProduct.ProductName, 
              tblhf.HFName, 
              case when tblClaim.ClaimStatus=1 then 'Rejected'
               when tblClaim.ClaimStatus=2 then 'Entered'
               when tblClaim.ClaimStatus=4 then 'Checked'
               when tblClaim.ClaimStatus=6 then 'Recommended'
                when tblClaim.ClaimStatus=8 then 'Processe'
               when tblClaim.ClaimStatus=9 then 'Forwaded'
               when tblClaim.ClaimStatus=16 then 'Valuated'
              else ''
               END as ApprovalStatus,
               tblClaim.Claimed as Entered,
              tblClaim.approved as Approved, 
              case when tblClaim.PaymentStatus=0 then 'Booked'
               when tblClaim.PaymentStatus=1 then 'Reject'
               when tblClaim.PaymentStatus=2 then 'Paid'
              
              else 'Idle'
               END as 'Payment Status',
              CONCAT(tblclaim.paymentDate, '.') as PaymentDate
            FROM 
              [tblClaim] 
              INNER JOIN [tblInsuree] ON (
                [tblClaim].[InsureeID] = [tblInsuree].[InsureeID]
              ) 
              LEFT OUTER JOIN [sosys_subproduct] ON (
                [tblClaim].[subProduct_id] = [sosys_subproduct].[id]
              ) 
              LEFT OUTER JOIN [tblProduct] ON (
                [tblClaim].[product_id] = [tblProduct].[ProdID]
              ) 
              JOIN [tblHF] on (
                [tblClaim].[HFID] =  [tblHF].[HfID]
              )
        """
        if fromDate and todate:
            print("719")
            query_string += f"""

            WHERE 
              (
                [tblClaim].[DateClaimed] >= '{fromDate}' 
                AND [tblClaim].[DateClaimed] <= '{todate}'
                )
            """
        if not fromDate:
            print("728")
            if todate:
                print("730")
                query_string += f""" 
                    WHERE [tblClaim].[DateClaimed] <= '{todate}' 
                """
        if not todate:
            print("735")
            if fromDate:
                print("737")
                query_string += f""" 
                    WHERE [tblClaim].[DateClaimed] >= '{fromDate}' 
                """
        if not fromDate:
            if not todate:
                print("742")
                query_string += f""" where 1=1"""
        if healthfacility_id or request.user.i_user.health_facility_id:
            query_string += f""" AND [tblClaim].[HFID] = {healthfacility_id if healthfacility_id else request.user.i_user.health_facility_id}"""  # if healthfacility_id else request.user.i_user.get('health_facility_id')}"""

        if product_id:
            query_string += f""" 

            AND tblClaim.product_id = {product_id}
            """
        if insuree_chfid:
            query_string += f""" 
                    AND tblInsuree.CHFID = '{insuree_chfid}' 
                """
        if claim_no:
            query_string += f""" 
                    AND tblclaim.ClaimCode = '{claim_no}' 
                """

        if claim_status:
            query_string += f""" 
                    AND tblclaim.ClaimStatus = '{claim_status}' 
                """
        if payment_status:
            query_string += f""" 
                    AND tblclaim.paymentStatus = '{payment_status}' 
                """
        else:
            query_string += f""" 
                 AND [tblClaim].[ValidityTo] IS NULL
               
            ORDER BY 
              [tblClaim].[DateClaimed] ASC

        """

        print("query String", query_string)
        return query_to_excel_download_helper(query_string)
    except Exception:
        print(traceback.format_exc())
    # for row in rows:
    #     data = (
    #         row.code,
    #         row.insuree.chf_id if row.insuree else "No Insuree found",
    #         row.insuree.other_names +' '+row.insuree.last_name if row.insuree else "No Insuree found",
    #         "No Scheme" if not row.product else row.product.name,
    #         "No Sub Scheme" if not row.subProduct else row.subProduct.sch_name_eng,
    #         row.date_claimed.strftime('%Y-%m-%d') if row.date_claimed else "",
    #         row.claimed,
    #         row.approved,
    #         statuses.get(row.status,"null"),
    #         payment_statuses.get(row.payment_status,"Booked") if row.status != 1 else "Reversed",
    #         row.payment_date.strftime('%Y-%m-%d') if row.payment_date else "",
    #         row.payment_remarks
    #         )
    #     l.append(data)
    # print('l____query', l)
    # for row in l:
    #     row_num += 1
    #     for col_num in range(len(row)):
    #         ws.write(row_num, col_num, row[col_num], font_style)

    # wb.save(response)
    # return response
