import datetime
import graphene
from core import prefix_filterset, ExtendedConnection, filter_validity
from graphene.utils.deduplicator import deflate
from graphene_django import DjangoObjectType
from insuree.schema import InsureeGQLType
from location.schema import HealthFacilityGQLType
from medical.schema import DiagnosisGQLType
from claim_batch.schema import BatchRunGQLType
from .apps import ClaimConfig
from claim.models import (ClaimDedRem, Claim, ClaimAdmin, Feedback, ClaimItem, ClaimService, ClaimAttachment,
                          ClaimAttachmentType)
from django.utils.translation import gettext as _
from django.core.exceptions import PermissionDenied


class ClaimDedRemGQLType(DjangoObjectType):
    """
    Details about Claim demands and remunerated amounts
    """
    class Meta:
        model = ClaimDedRem
        interfaces = (graphene.relay.Node,)


class ClaimAdminGQLType(DjangoObjectType):
    """
    Details about a Claim Administrator
    """

    class Meta:
        model = ClaimAdmin
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "uuid": ["exact"],
            "code": ["exact", "icontains"],
            "last_name": ["exact", "icontains"],
            "other_names": ["exact", "icontains"],
            **prefix_filterset("health_facility__", HealthFacilityGQLType._meta.filter_fields),
        }
        connection_class = ExtendedConnection

    @classmethod
    def get_queryset(cls, queryset, info):
        queryset = queryset.filter(*filter_validity())
        return queryset


class ClaimGQLType(DjangoObjectType):
    """
    Main element for a Claim. It can contain items and/or services.
    The filters are possible on BatchRun, Insuree, HealthFacility, Admin and ICD in addition to the Claim fields
    themselves.
    """

    attachments_count = graphene.Int()
    client_mutation_id = graphene.String()
    date_processed_to = graphene.Date()
    restore_id = graphene.Int()
    
    def resolve_insuree(self, info):
        if not info.context.user.has_perms(ClaimConfig.gql_query_claims_perms):
            raise PermissionDenied(_("unauthorized"))
        if "insuree_loader" in info.context.dataloaders and self.insuree_id:
            return info.context.dataloaders["insuree_loader"].load(self.insuree_id)
        return self.insuree

    def resolve_health_facility(self, info):
        if not info.context.user.has_perms(ClaimConfig.gql_query_claims_perms):
            raise PermissionDenied(_("unauthorized"))
        if (
            "health_facility_loader" in info.context.dataloaders
            and self.health_facility_id
        ):
            return info.context.dataloaders["health_facility_loader"].load(
                self.health_facility_id
            )
        return self.health_facility
    
    def resolve_restore_id(self, info):
        return self.restore_id
        
        
    class Meta:
        model = Claim
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "uuid": ["exact"],
            "code": ["exact", "istartswith", "icontains", "iexact"],
            "status": ["exact", "gt"],
            "date_claimed": ["exact", "lt", "lte", "gt", "gte"],
            "date_from": ["exact", "lt", "lte", "gt", "gte"],
            "date_to": ["exact", "lt", "lte", "gt", "gte"],
            "date_processed": ["exact", "lt", "lte", "gt", "gte"],
            "feedback_status": ["exact"],
            "review_status": ["exact"],
            "claimed": ["exact", "lt", "lte", "gt", "gte"],
            "approved": ["exact", "lt", "lte", "gt", "gte"],
            "visit_type": ["exact"],
            "attachments_count__value": ["exact", "lt", "lte", "gt", "gte"],
            **prefix_filterset("icd__", DiagnosisGQLType._meta.filter_fields),
            **prefix_filterset("admin__", ClaimAdminGQLType._meta.filter_fields),
            **prefix_filterset("health_facility__", HealthFacilityGQLType._meta.filter_fields),
            **prefix_filterset("insuree__", InsureeGQLType._meta.filter_fields),
            **prefix_filterset("batch_run__", BatchRunGQLType._meta.filter_fields)
        }
        connection_class = ExtendedConnection

    def resolve_attachments_count(self, info):
        if not info.context.user.has_perms(ClaimConfig.gql_query_claims_perms):
            raise PermissionDenied(_("unauthorized"))
        return self.attachments.filter(legacy_id__isnull=True).filter(validity_to__isnull=True).count()

    def resolve_items(self, info):
        if not info.context.user.has_perms(ClaimConfig.gql_query_claims_perms):
            raise PermissionDenied(_("unauthorized"))
        return self.items.filter(legacy_id__isnull=True).filter(validity_to__isnull=True)

    def resolve_services(self, info):
        if not info.context.user.has_perms(ClaimConfig.gql_query_claims_perms):
            raise PermissionDenied(_("unauthorized"))
        return self.services.filter(legacy_id__isnull=True).filter(validity_to__isnull=True)

    def resolve_client_mutation_id(self, info):
        if not info.context.user.has_perms(ClaimConfig.gql_query_claims_perms):
            raise PermissionDenied(_("unauthorized"))
        claim_mutation = self.mutations.select_related(
            'mutation').filter(mutation__status=0).first()
        return claim_mutation.mutation.client_mutation_id if claim_mutation else None

    @classmethod
    def get_queryset(cls, queryset, info):
        return Claim.get_queryset(queryset, info).all()


class ClaimAttachmentGQLType(DjangoObjectType):
    doc = graphene.String()

    class Meta:
        model = ClaimAttachment
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "type": ["exact", "icontains"],
            "title": ["exact", "icontains"],
            "date": ["exact", "lt", "lte", "gt", "gte"],
            "filename": ["exact", "icontains"],
            "mime": ["exact", "icontains"],
            "general_type": ["exact", "icontains"],
            "url": ["exact", "icontains"],
            **prefix_filterset("claim__", ClaimGQLType._meta.filter_fields),
        }
        connection_class = ExtendedConnection

    @classmethod
    def get_queryset(cls, queryset, info):
        queryset = queryset.filter(*filter_validity())
        return queryset


class ClaimAttachmentTypeGQLType(DjangoObjectType):
    class Meta:
        model = ClaimAttachmentType
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "claim_general_type": ["exact"]
        }
        connection_class = ExtendedConnection


class FeedbackGQLType(DjangoObjectType):
    class Meta:
        model = Feedback


class ClaimItemGQLType(DjangoObjectType):
    """
    Contains the items within a specific Claim
    """

    class Meta:
        model = ClaimItem


class ClaimServiceGQLType(DjangoObjectType):
    """
    Contains the services within a specific Claim
    """

    class Meta:
        model = ClaimService

class HospitalTotalClaim(graphene.ObjectType):
    hospital_name = graphene.String()
    total_claim = graphene.Int()

class TopClaimType(graphene.ObjectType):
    claim_id = graphene.ID()
    claimed_amount = graphene.Float()
    hospital_name = graphene.String()


class RegisteredContributorsGQLType(graphene.ObjectType):
    male_count = graphene.Int()
    female_count = graphene.Int()    

class DashboardGQLType(graphene.ObjectType):
    # contains summary for dashboard graphs 
    top_claims = graphene.List(TopClaimType)
    total_claims_by_hospital = graphene.List(HospitalTotalClaim)
    registered_contributors = graphene.Field(RegisteredContributorsGQLType)
    Medical_in_progress = graphene.Int()
    Medical_settled = graphene.Int()
    Medical_claim_application = graphene.Int()
    Medical_rejected = graphene.Int()
    Medical_forwarded = graphene.Int()
    Medical_entered = graphene.Int()

    # Data set 2
    work_place_accident = graphene.Int()
    accident = graphene.Int()
    occupational_disease = graphene.Int()
    other = graphene.Int()

    #Data set 3
    range1 = graphene.Int() #1-100000
    range2 = graphene.Int() #100001-200000
    range3 = graphene.Int() #200001-300000
    range4 = graphene.Int() #300001-400000
    range5 = graphene.Int() #above 400000
