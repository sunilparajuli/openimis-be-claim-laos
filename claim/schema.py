import graphene
from enum import Enum

from core.models import Officer, MutationLog
from insuree.models import Insuree
from location.models import HealthFacility, Location, LocationManager
from .services import check_unique_claim_code
import django
from core.schema import signal_mutation_module_validate, signal_mutation_module_after_mutating
from django.db.models import OuterRef, Subquery, Avg, Q
import graphene_django_optimizer as gql_optimizer
from core.schema import OrderedDjangoFilterConnectionField, OfficerGQLType
from core import filter_validity
from django.db.models.functions import Cast

from .models import ClaimMutation
from django.utils.translation import gettext as _
from graphene_django.filter import DjangoFilterConnectionField
import ast

# We do need all queries and mutations in the namespace here.
from .gql_queries import *  # lgtm [py/polluting-import]
from .gql_mutations import *  # lgtm [py/polluting-import]


class HospitalClaimDataType(graphene.ObjectType):
    hospital = graphene.String()
    acceptedClaims = graphene.Int()
    rejectedClaims = graphene.Int()

class Query(graphene.ObjectType):
    claims = OrderedDjangoFilterConnectionField(
        ClaimGQLType,
        diagnosisVariance=graphene.Int(),
        code_is_not=graphene.String(),
        orderBy=graphene.List(of_type=graphene.String),
        items=graphene.List(of_type=graphene.String),
        services=graphene.List(of_type=graphene.String),
        json_ext=graphene.JSONString(),
        attachment_status=graphene.Int(required=False),
        care_type=graphene.String(required=False),
        show_restored=graphene.Boolean(required=False)
        )
    health_facilities = graphene.List(HospitalClaimDataType)
    hospital_claim_data = graphene.List(graphene.List(graphene.String))
    registered_contributors = graphene.Field(RegisteredContributorsGQLType)


    def resolve_registered_contributors(root, info):
        # Count male contributors
        male_count = Insuree.objects.filter(gender__icontains='M', validity_to=None).count()
        
        # Count female contributors
        female_count = Insuree.objects.filter(gender__icontains='F', validity_to=None).count()

        # Return the counts
        return RegisteredContributorsGQLType(
            male_count=male_count,
            female_count=female_count
        )    

    def resolve_health_facilities(self, info):
        return HealthFacility.objects.all()
    def resolve_hospital_claim_data(self, info):
        data = [['Hospital', 'Accepted Claims', 'Rejected Claims']]
        claims = Claim.objects.filter(status__in=[2, 1])

        for claim in claims:
            hospital_name = claim.health_facility.name
            accepted = claim.status > 1
            rejected = claim.status == 1

            if accepted:
                data.append([hospital_name, claim.claimed, 0])
            elif rejected:
                data.append([hospital_name, 0, claim.claimed])

        return data
    dashboard = graphene.Field(DashboardGQLType)
    from django.db.models import Count, Q

    def resolve_dashboard(root, info):
        # Fetching all counts in a single query
        total_claims_by_hospital = (
            Claim.objects
            .values('health_facility__name')
            .annotate(total_claim=Count('id'))
        )

        # Constructing list of HospitalTotalClaim objects
        total_claims_data = [
            HospitalTotalClaim(
                hospital_name=entry['health_facility__name'],
                total_claim=entry['total_claim']
            )
            for entry in total_claims_by_hospital
        ]        
        top_claims = (
            Claim.objects
            .select_related('health_facility')
            .filter(validity_to__isnull=True)
            .order_by('-claimed')[:10]
        )
        top_claims_data = [
            {
                'claim_id': claim.id,
                'claimed_amount': claim.claimed,
                'hospital_name': claim.health_facility.name if claim.health_facility else None
            }
            for claim in top_claims
        ]
        claim_counts = (
            Claim.objects
            .filter(validity_to__isnull=True)
            .aggregate(
                medical_claim_application=Count('pk'),
                medical_forwarded=Count('pk', filter=Q(status=9)),
                medical_valuated=Count('pk', filter=Q(status=16)),
                medical_reject=Count('pk', filter=Q(status=1)),
                medical_enter=Count('pk', filter=Q(status=2)),
                medical_checked=Count('pk', filter=Q(status=6)),
                range1=Count('pk', filter=Q(approved__gte=1, approved__lte=100000)),
                range2=Count('pk', filter=Q(approved__gte=100001, approved__lte=200000)),
                range3=Count('pk', filter=Q(approved__gte=200001, approved__lte=300000)),
                range4=Count('pk', filter=Q(approved__gte=300001, approved__lte=400000)),
                range5=Count('pk', filter=Q(approved__gte=400001))
            )
        )

        # Constructing DashboardGQLType instance with fetched counts
        return DashboardGQLType(
            top_claims=top_claims_data,
            total_claims_by_hospital=total_claims_data,
            Medical_in_progress=claim_counts['medical_checked'],
            Medical_settled=claim_counts['medical_valuated'],
            Medical_claim_application=claim_counts['medical_claim_application'],
            Medical_rejected=claim_counts['medical_reject'],
            Medical_forwarded=claim_counts['medical_forwarded'],
            Medical_entered=claim_counts['medical_enter'],
            range1=claim_counts['range1'],
            range2=claim_counts['range2'],
            range3=claim_counts['range3'],
            range4=claim_counts['range4'],
            range5=claim_counts['range5'],
        )


    claim = graphene.Field(
        ClaimGQLType, 
        id=graphene.Int(), 
        uuid=graphene.UUID()
    )

    claim_attachments = DjangoFilterConnectionField(
        ClaimAttachmentGQLType
    )
    claim_admins = DjangoFilterConnectionField(
        ClaimAdminGQLType,
        search=graphene.String(),
        region_uuid=graphene.String(),
        district_uuid=graphene.String()
    )
    claim_officers = DjangoFilterConnectionField(
        OfficerGQLType, search=graphene.String()
    )

    insuree_name_by_chfid = graphene.String(
        chfId=graphene.String(required=True)
    )

    validate_claim_code = graphene.Field(
        graphene.Boolean,
        claim_code=graphene.String(required=True),
        description="Checks that the specified claim code is unique."
    )
    fsp_from_claim = graphene.Field(
        HealthFacilityGQLType,
        insuree_code=graphene.String(required=True),
        date_claimed=graphene.Date(required=True),
        description="Return FSP of insuree during creation of the claim."
    )

    claim_with_same_diagnosis = OrderedDjangoFilterConnectionField(
        ClaimGQLType,
        icd=graphene.String(required=True),
        chfid=graphene.String(required=True),
        description="Return last claim (date claimed) with identical diagnosis for given insuree."
    )

    claim_attachment_type = DjangoFilterConnectionField(
        ClaimAttachmentTypeGQLType
    )

    def resolve_insuree_name_by_chfid(self, info, **kwargs):
        if not info.context.user.has_perms(ClaimConfig.gql_mutation_create_claims_perms)\
                and not info.context.user.has_perms(ClaimConfig.gql_mutation_update_claims_perms):
            raise PermissionDenied(_("unauthorized"))
        chf_id = kwargs.get('chfId')
        insuree = Insuree.objects\
            .filter(validity_to__isnull=True, chf_id=chf_id)\
            .values('last_name', 'other_names')\
            .first()
        if insuree:
            insuree_name = f"{insuree['other_names']} {insuree['last_name']}"
        else:
            insuree_name = ""
        return insuree_name

    def resolve_validate_claim_code(self, info, **kwargs):
        if not info.context.user.has_perms(ClaimConfig.gql_query_claims_perms):
            raise PermissionDenied(_("unauthorized"))
        errors = check_unique_claim_code(code=kwargs['claim_code'])
        return False if errors else True

    def resolve_claim(self, info, id=None, uuid=None, **kwargs):
        if (
            not info.context.user.has_perms(ClaimConfig.gql_query_claims_perms)
            and settings.ROW_SECURITY
        ):
            raise PermissionDenied(_("unauthorized"))

        if id is not None:
            return Claim.objects.get(id=id)
        if uuid is not None:
            return Claim.objects.get(uuid=uuid)

    def resolve_claims(self, info, **kwargs):
        class AttachmentStatusEnum(Enum):
            NONE = 0
            WITH = 1
            WITHOUT = 2
        if (
            not info.context.user.has_perms(ClaimConfig.gql_query_claims_perms)
            and settings.ROW_SECURITY
        ):
            raise PermissionDenied(_("unauthorized"))
        query = Claim.objects
        filters = []

        show_restored = kwargs.get("show_restored", None)
        if show_restored:
            filters.append(Q(restore__isnull=False))

        items = kwargs.get("items", None)
        services = kwargs.get("services", None)

        if items:
            filters.append(Q(items__item__code__in=items))

        if services:
            filters.append(Q(services__service__code__in=services))

        attachment_status = kwargs.get("attachment_status", 0)
        if attachment_status == AttachmentStatusEnum.WITH.value:
            filters.append(Q(attachments__isnull=False))
        elif attachment_status == AttachmentStatusEnum.WITHOUT.value:
            filters.append(Q(attachments__isnull=True))

        care_type = kwargs.get("care_type", None)

        if care_type:
            filters.append(Q(care_type=care_type))

        json_ext = kwargs.get("json_ext", None)

        if json_ext:
            filters.append(Q(json_ext__jsoncontains=json_ext))
        variance = kwargs.get("diagnosisVariance", None)
        if variance:
            from core import datetime, datetimedelta

            last_year = datetime.date.today() + datetimedelta(years=-1)
            diag_avg = (
                Claim.objects.filter(*filter_validity(**kwargs))
                .filter(date_claimed__gt=last_year)
                .values("icd__code")
                .filter(icd__code=OuterRef("icd__code"))
                .annotate(diag_avg=Avg("approved"))
                .values("diag_avg")
            )
            variance_filter = Q(claimed__gt=(
                1 + variance / 100) * Subquery(diag_avg))
            if not ClaimConfig.gql_query_claim_diagnosis_variance_only_on_existing:
                diags = (
                    Claim.objects.filter(*filter_validity(**kwargs))
                    .filter(date_claimed__gt=last_year)
                    .values("icd__code")
                    .distinct()
                )
                variance_filter = Q(variance_filter | ~Q(icd__code__in=diags))
            filters.append(variance_filter)    
        #filtered already in get_queryser
        #query = query.filter(
        #            LocationManager().build_user_location_filter_query( info.context.user._u, prefix='health_facility__location') 
        #        )
        code_is_not = kwargs.get("code_is_not", None)
        
        if len(filters):
            query = query.filter(*filters)   
        if code_is_not:
            query = query.exclude(code=code_is_not)
        
        if len(filters) == 0 and not code_is_not:
            query = query.all()
        return gql_optimizer.query(query, info)

    def resolve_claim_attachments(self, info, **kwargs):
        if not info.context.user.has_perms(ClaimConfig.gql_query_claims_perms):
            raise PermissionDenied(_("unauthorized"))

    def resolve_claim_admins(
            self,
            info,
            search=None,
            **kwargs
    ):
        if not info.context.user.has_perms(
                ClaimConfig.gql_query_claim_admins_perms
        ):
            raise PermissionDenied(_("unauthorized"))

        hf_filters = [*filter_validity(**kwargs)]
        district_uuid = kwargs.get('district_uuid', None)
        region_uuid = kwargs.get('region_uuid', None)
        if district_uuid is not None:
            hf_filters += [Q(location__uuid=district_uuid)]
        elif region_uuid is not None:
            hf_filters += [Q(location__parent__uuid=region_uuid)]
        if settings.ROW_SECURITY:
            q = LocationManager().build_user_location_filter_query( info.context.user._u, prefix='location', loc_types=['D'])
            if q:
                hf_filters += [q]

        user_health_facility = HealthFacility.objects.filter(*hf_filters)

        filters = [*filter_validity(**kwargs)]
        if user_health_facility:
            filters += [Q(health_facility__in=user_health_facility)]

        if search:
            filters += [Q(code__icontains=search) |
                        Q(last_name__icontains=search) |
                        Q(other_names__icontains=search)]

        return ClaimAdmin.objects.filter(*filters)

    def resolve_claim_officers(self, info, search=None, **kwargs):
        if not info.context.user.has_perms(ClaimConfig.gql_query_claim_officers_perms):
            raise PermissionDenied(_("unauthorized"))

        qs = Officer.objects

        if search is not None:
            qs = qs.filter(
                Q(code__icontains=search)
                | Q(last_name__icontains=search)
                | Q(other_names__icontains=search)
            )
        return qs

    def resolve_fsp_from_claim(self, info, **kwargs):
        if not info.context.user.has_perms(ClaimConfig.gql_query_claim_officers_perms):
            raise PermissionDenied(_("unauthorized"))
        result = Insuree.objects.filter(
            chf_id=kwargs['insuree_code'],
            *filter_validity(validity=kwargs['date_claimed']),
        ).first().health_facility
        return result

    def resolve_claim_with_same_diagnosis(self, info, **kwargs):
        if not info.context.user.has_perms(ClaimConfig.gql_query_claim_officers_perms):
            raise PermissionDenied(_("unauthorized"))

        qs = Claim.objects.filter(icd__code=kwargs['icd'], icd__validity_to__isnull=True,
                                  insuree__chf_id=kwargs['chfid'], insuree__validity_to__isnull=True,
                                  validity_to__isnull=True).order_by("date_claimed")
        return qs


class Mutation(graphene.ObjectType):
    create_claim = CreateClaimMutation.Field()
    update_claim = UpdateClaimMutation.Field()
    create_claim_attachment = CreateAttachmentMutation.Field()
    update_claim_attachment = UpdateAttachmentMutation.Field()
    delete_claim_attachment = DeleteAttachmentMutation.Field()
    submit_claims = SubmitClaimsMutation.Field()
    select_claims_for_feedback = SelectClaimsForFeedbackMutation.Field()
    deliver_claim_feedback = DeliverClaimFeedbackMutation.Field()
    bypass_claims_feedback = BypassClaimsFeedbackMutation.Field()
    skip_claims_feedback = SkipClaimsFeedbackMutation.Field()
    select_claims_for_review = SelectClaimsForReviewMutation.Field()
    save_claim_review = SaveClaimReviewMutation.Field()
    deliver_claims_review = DeliverClaimsReviewMutation.Field()
    bypass_claims_review = BypassClaimsReviewMutation.Field()
    skip_claims_review = SkipClaimsReviewMutation.Field()
    process_claims = ProcessClaimsMutation.Field()
    delete_claims = DeleteClaimsMutation.Field()



def on_claim_mutation(sender, **kwargs):
    uuids = kwargs["data"].get("uuids", [])
    if not uuids:
        uuid = kwargs["data"].get("claim_uuid", None)
        uuids = [uuid] if uuid else []
    if not uuids:
        return []
    impacted_claims = Claim.objects.filter(uuid__in=uuids).all()
    for claim in impacted_claims:
        ClaimMutation.objects.create(
            claim=claim, mutation_id=kwargs["mutation_log_id"])
    return []


def on_claim_after_mutation(sender, **kwargs):
    if kwargs.get('error_messages', None):
        return []
    elif kwargs.get('mutation_class', None) != 'CreateClaimMutation':
        return []
    if 'data' in kwargs and kwargs['data'].get('autogenerate'):
        try:
            mutation_client_id = kwargs.get('data')['client_mutation_id']
            mutation_log = MutationLog.objects.filter(client_mutation_id=mutation_client_id).first()
            mutation_log.client_mutation_label = kwargs['data']['client_mutation_label']
            mutation_log.autogenerated_code = kwargs['data']['code']
            mutation_log.save()
            return []
        except KeyError as e:
            logger.error("Client Mutation ID not found in claim signal after mutation, error: ", e)
    return []


def bind_signals():
    signal_mutation_module_validate["claim"].connect(on_claim_mutation)
    signal_mutation_module_after_mutating["claim"].connect(on_claim_after_mutation)
