# -*- coding: utf-8 -*-
"""API Serializers"""
from __future__ import unicode_literals
from collections import defaultdict, OrderedDict

from django.contrib.auth.models import User
from rest_framework.serializers import (
    BooleanField, ChoiceField, CurrentUserDefault, DateField, DateTimeField,
    IntegerField, SerializerMethodField, SlugField, ValidationError)
from rest_framework.serializers import Serializer as BaseSerializer

from .drf_fields import (
    CurrentHistoryField, HistoricalObjectField, HistoryField,
    MPTTRelationField, OptionalCharField, OptionalIntegerField,
    PrimaryKeyRelatedField, TranslatedTextField)
from .history import Changeset
from .models import (
    Browser, Feature, Maturity, Section, Specification, Support, Version)
from .validators import VersionAndStatusValidator


class BaseMeta(object):
    pass


class Serializer(BaseSerializer):
    """Common serializer functionality

    Inspired by ModelSerializer, which has a bit too much magic and
    too few customization hooks.
    """

    FIELD_TYPES = ('property', 'link', 'many', 'sorted', 'serializer field')
    META_WRITABLE = ('always', 'never', 'at update', 'at create')

    def __init__(self, *args, **kwargs):
        """Initialize the Serializer"""
        # Initialize fields from Meta and the action ('create', 'update', etc)
        view = kwargs.get('context', {}).get('view', None)
        self.action = view and view.action
        self.init_fields_with_action(self.action)

        # Run standard DRF initialization
        super(Serializer, self).__init__(*args, **kwargs)

    def init_fields_with_action(self, action):
        """Merge Meta.fields with declared fields and view action."""
        assert not hasattr(self, 'field_data')

        # Remove omitted fields
        omitted_fields = set(getattr(self.Meta, 'omit_fields', ()))
        for field_name in omitted_fields:
            del self.fields[field_name]

        declared_fields = set(self.fields.keys())
        meta_fields = set(self.Meta.fields.keys()) - omitted_fields
        assert declared_fields == meta_fields, \
            '%s != %s' % (sorted(declared_fields), sorted(meta_fields))

        # Determine modification based on view action
        mod_to_read_only = None
        if action in ('list', 'create'):
            mod_to_read_only = 'at update'
        elif action in ('update', 'partial_update'):
            mod_to_read_only = 'at create'

        all_field_data = OrderedDict()
        for name, field in self.fields.items():
            metadata = self.Meta.fields[name]

            # Validate that read_only / writable agree
            default_writable = 'never' if field.read_only else 'always'
            writable = metadata.get('writable', default_writable)
            assert writable in self.META_WRITABLE
            if writable == 'never':
                assert getattr(field, 'read_only', True), writable
            else:
                assert not field.read_only
                if writable == mod_to_read_only:
                    field.read_only = True

            # Create field data
            field_data = {
                'type': metadata.get('type', 'property'),
                'writable': not getattr(field, 'read_only', True),
                'archived': metadata.get('archived', True),
            }

            # Validate type
            assert field_data['type'] in self.FIELD_TYPES
            if field_data['type'] == 'sorted':
                assert hasattr(self, 'update_' + name)

            # Validate boolean fields
            assert field_data['writable'] in (True, False)
            assert field_data['archived'] in (True, False)

            all_field_data[name] = field_data
        self.field_data = all_field_data

    @property
    def writable_field_names(self):
        """Return a dict of field types to a list of field names."""
        write_names = defaultdict(list)
        for name, field_data in self.field_data.items():
            if field_data['writable']:
                write_names[field_data['type']].append(name)
        return write_names

    def validate_history_current(self, data):
        """Serialize historical data if requested."""
        if data.instance != self.instance:
            raise ValidationError('Invalid history ID for this object')

        current_history = self.instance.history.all()[0]
        if data != current_history:
            self.historical_data = OrderedDict()
            archived_fields = [
                name for name, field_data in self.field_data.items()
                if field_data['archived']]
            for field in archived_fields:
                self.historical_data[field] = getattr(data, field)
        return data

    def create(self, validated_data):
        """Create a new instance."""
        # Assemble all writable fields
        write_names = self.writable_field_names

        # API doesn't have all cases
        assert not write_names['many']
        assert not write_names['serializer field']

        # Create the on-instance data
        at_create_names = set(write_names['property'] + write_names['link'])
        create_data = dict([
            (k, v) for k, v in validated_data.items() if k in at_create_names])
        instance = self.Meta.model.objects.create(**create_data)

        # Create the sorted to-many relations
        for name in write_names['sorted']:
            if name in validated_data:
                update_method = getattr(self, 'update_' + name)
                update_method(name, instance, validated_data)

        return instance

    def update(self, instance, validated_data):
        """Update an instance."""
        data = getattr(self, 'historical_data', {})
        data.update(validated_data)

        write_names = self.writable_field_names

        # Update the on-instance data
        simple_updates = (
            write_names['property'] + write_names['link'] +
            write_names['many'])
        for name in simple_updates:
            old_value = getattr(instance, name, None)
            new_value = data.get(name, old_value)
            if old_value != new_value:
                setattr(instance, name, new_value)

        # Update sorted relationships
        for name in write_names['sorted']:
            if name in data:
                update_method = getattr(self, 'update_' + name)
                update_method(name, instance, data)

        instance.save()
        return instance


#
# "Regular" Serializers
#
class BrowserSerializer(Serializer):
    """Browser Serializer"""

    id = IntegerField(label='ID', read_only=True)
    slug = SlugField(
        help_text='Unique, human-friendly slug.', max_length=50)
    name = TranslatedTextField(
        help_text='Branding name of browser, client, or platform.',
        required=True, style={'base_template': 'textarea.html'})
    note = TranslatedTextField(
        help_text='Extended information about browser, client, or platform.',
        allow_blank=True, allow_null=True, required=False,
        style={'base_template': 'textarea.html'})
    history = HistoryField(many=True, read_only=True)
    history_current = CurrentHistoryField()
    versions = PrimaryKeyRelatedField(
        many=True, queryset=Version.objects.all())

    def update_versions(self, field, instance, validated_data):
        """Reorder versions."""
        versions = validated_data.get(field)
        if versions:
            v_pks = [v.pk for v in versions]
            current_order = instance.get_version_order()
            if v_pks != current_order:
                instance.set_version_order(v_pks)

    class Meta(BaseMeta):
        model = Browser
        fields = OrderedDict((
            ('id', {}),
            ('slug', {
                'writable': 'at create'}),
            ('name', {}),
            ('note', {}),
            ('history_current', {
                'type': 'serializer field',
                'writable': 'at update',
                'archived': False}),
            ('history', {
                'type': 'many',
                'archived': False}),
            ('versions', {
                'type': 'sorted',
                'writable': 'at update',
                'archived': False}),
        ))


class FeatureSerializer(Serializer):
    """Feature Serializer"""
    url = SerializerMethodField()  # Used in ViewFeatureListSerializer
    id = IntegerField(label='ID', read_only=True)
    slug = SlugField(
        help_text='Unique, human-friendly slug.', max_length=50)
    mdn_uri = TranslatedTextField(
        help_text='The URI of the MDN page that documents this feature.',
        allow_blank=True, allow_null=True, required=False,
        style={'base_template': 'textarea.html'})
    experimental = BooleanField(
        help_text=(
            'True if a feature is considered experimental, such as being'
            ' non-standard or part of an non-ratified spec.'),
        required=False)
    standardized = BooleanField(
        help_text=(
            "True if a feature is described in a standards-track spec,"
            " regardless of the spec's maturity."),
        required=False)
    stable = BooleanField(
        help_text=(
            'True if a feature is considered suitable for production'
            ' websites.'),
        required=False)
    obsolete = BooleanField(
        help_text=(
            'True if a feature should not be used in new development.'),
        required=False)
    name = TranslatedTextField(
        help_text='Feature name, in canonical or localized form.',
        allow_canonical=True, required=True,
        style={'base_template': 'textarea.html'})
    sections = PrimaryKeyRelatedField(
        default=[], many=True, queryset=Section.objects.all())
    supports = PrimaryKeyRelatedField(many=True, read_only=True)
    parent = PrimaryKeyRelatedField(
        help_text='Feature set that contains this feature',
        allow_null=True, queryset=Feature.objects.all(), required=False)
    children = MPTTRelationField(many=True, read_only=True)
    history_current = CurrentHistoryField(read_only=None)
    history = HistoryField(many=True, read_only=True)

    def update_sections(self, field, instance, validated_data):
        """Reorder sections"""
        new_values = validated_data.get(field)
        if new_values:
            new_pks = [value.pk for value in new_values]
            current_pks = getattr(instance, field).values_list('pk', flat=True)
            if new_pks != current_pks:
                setattr(instance, field, new_values)

    class Meta(BaseMeta):
        model = Feature
        fields = OrderedDict((
            ('url', {'archived': False}),
            ('id', {}),
            ('slug', {'writable': 'at create'}),
            ('mdn_uri', {}),
            ('experimental', {}),
            ('standardized', {}),
            ('stable', {}),
            ('obsolete', {}),
            ('name', {}),
            ('sections', {'type': 'sorted', 'archived': False}),
            ('supports', {'type': 'many', 'archived': False}),
            ('parent', {'type': 'link'}),
            ('children', {'type': 'many', 'archived': False}),
            ('history_current', {
                'type': 'serializer field',
                'writable': 'at update',
                'archived': False}),
            ('history', {
                'type': 'many',
                'archived': False}),
        ))
        omit_fields = ('url',)


class MaturitySerializer(Serializer):
    """Specification Maturity Serializer"""
    id = IntegerField(label='ID', read_only=True)
    slug = SlugField(
        help_text=(
            'Unique, human-friendly slug, sourced from the KumaScript'
            ' macro Spec2'),
        max_length=50)
    name = TranslatedTextField(
        help_text='Name of maturity',
        required=True, style={'base_template': 'textarea.html'})
    specifications = PrimaryKeyRelatedField(many=True, read_only=True)
    history_current = CurrentHistoryField(read_only=None)
    history = HistoryField(many=True, read_only=True)

    class Meta(BaseMeta):
        model = Maturity
        fields = OrderedDict((
            ('id', {}),
            ('slug', {}),
            ('name', {}),
            ('specifications', {
                'archived': False}),
            ('history_current', {
                'type': 'serializer field',
                'writable': 'at update',
                'archived': False}),
            ('history', {
                'type': 'many',
                'archived': False}),
        ))


class SectionSerializer(Serializer):
    """Specification Section Serializer"""
    id = IntegerField(label='ID', read_only=True)
    number = TranslatedTextField(
        allow_blank=True, help_text='Section number', required=False,
        style={'base_template': 'textarea.html'})
    name = TranslatedTextField(
        help_text='Name of section, without section number',
        required=True, style={'base_template': 'textarea.html'})
    subpath = TranslatedTextField(
        help_text=(
            'A subpage (possible with an #anchor) to get to the subsection'
            ' in the specification.'),
        allow_blank=True, required=False,
        style={'base_template': 'textarea.html'})
    note = TranslatedTextField(
        help_text='Notes for this section',
        allow_blank=True, required=False,
        style={'base_template': 'textarea.html'})
    specification = PrimaryKeyRelatedField(
        queryset=Specification.objects.all())
    features = PrimaryKeyRelatedField(
        default=[], many=True, queryset=Feature.objects.all())
    history_current = CurrentHistoryField(read_only=False)
    history = HistoryField(many=True, read_only=True)

    class Meta(BaseMeta):
        model = Section
        fields = OrderedDict((
            ('id', {}),
            ('number', {}),
            ('name', {}),
            ('subpath', {}),
            ('note', {}),
            ('specification', {}),
            ('features', {
                'type': 'many',
                'archived': False}),
            ('history_current', {
                'type': 'serializer field',
                'writable': 'at update',
                'archived': False}),
            ('history', {
                'type': 'many',
                'archived': False}),
        ))


class SpecificationSerializer(Serializer):
    """Specification Serializer"""

    id = IntegerField(label='ID', read_only=True)
    slug = SlugField(help_text='Unique, human-friendly slug', max_length=50)
    mdn_key = OptionalCharField(
        help_text='Key used in the KumaScript macro SpecName',
        allow_blank=True, max_length=30, required=False)
    name = TranslatedTextField(
        help_text='Name of specification', required=True,
        style={'base_template': 'textarea.html'})
    uri = TranslatedTextField(
        help_text='Specification URI, without subpath and anchor',
        required=True, style={'base_template': 'textarea.html'})
    maturity = PrimaryKeyRelatedField(queryset=Maturity.objects.all())
    sections = PrimaryKeyRelatedField(
        default=[], many=True, queryset=Section.objects.all())
    history_current = CurrentHistoryField(read_only=None)
    history = HistoryField(many=True, read_only=True)

    def update_sections(self, field, instance, data):
        sections = data.get(field)
        if sections:
            s_pks = [s.pk for s in sections]
            current_order = instance.get_section_order()
            if s_pks != current_order:
                instance.set_section_order(s_pks)

    class Meta(BaseMeta):
        model = Specification
        fields = OrderedDict((
            ('id', {}),
            ('slug', {}),
            ('mdn_key', {}),
            ('name', {}),
            ('uri', {}),
            ('maturity', {}),
            ('sections', {
                'type': 'sorted',
                'writable': 'at update',
                'archived': False}),
            ('history_current', {
                'type': 'serializer field',
                'writable': 'at update',
                'archived': False}),
            ('history', {
                'type': 'many',
                'archived': False}),
        ))
        # update_only_fields = ('history', 'history_current', 'sections')
        # archived_fields = [
        #    'slug', 'mdn_key', 'name', 'uri', 'maturity']
        # writable_fields = archived_fields + ['sections']


class SupportSerializer(Serializer):
    """Support Serializer"""
    id = IntegerField(label='ID', read_only=True)
    version = PrimaryKeyRelatedField(
        queryset=Version.objects.all(), required=True)
    feature = PrimaryKeyRelatedField(
        queryset=Feature.objects.all(), required=True)
    support = ChoiceField(
        help_text='Does the browser version support this feature?',
        choices=[(c, c) for c in ('yes', 'no', 'partial', 'unknown')],
        required=False)
    prefix = OptionalCharField(
        help_text='Prefix to apply to the feature name.',
        allow_blank=True, max_length=20, required=False)
    prefix_mandatory = BooleanField(
        help_text='Is the prefix required?', required=False)
    alternate_name = OptionalCharField(
        help_text='Alternate name for this feature.',
        allow_blank=True, max_length=50, required=False)
    alternate_mandatory = BooleanField(
        help_text='Is the alternate name required?', required=False)
    requires_config = OptionalCharField(
        help_text='A configuration string to enable the feature.',
        allow_blank=True, max_length=100, required=False)
    default_config = OptionalCharField(
        help_text='The configuration string in the shipping browser.',
        max_length=100, required=False, allow_blank=True)
    protected = BooleanField(
        help_text=(
            "True if feature requires additional steps to enable in order"
            " to protect the user's security or privacy."),
        required=False)
    note = TranslatedTextField(
        help_text='Notes for this support',
        allow_blank=True, allow_null=True, required=False,
        style={'base_template': 'textarea.html'})
    history_current = CurrentHistoryField(read_only=None)
    history = HistoryField(many=True, read_only=True)

    # TODO: Unique together version/feature

    class Meta(BaseMeta):
        model = Support
        fields = OrderedDict((
            ('id', {}),
            ('version', {}),
            ('feature', {}),
            ('support', {}),
            ('prefix', {}),
            ('prefix_mandatory', {}),
            ('alternate_name', {}),
            ('alternate_mandatory', {}),
            ('requires_config', {}),
            ('default_config', {}),
            ('protected', {}),
            ('note', {}),
            ('history_current', {
                'type': 'serializer field',
                'writable': 'at update',
                'archived': False}),
            ('history', {
                'type': 'many',
                'archived': False}),
        ))


class VersionSerializer(Serializer):
    """Browser Version Serializer"""
    id = IntegerField(label='ID', read_only=True)
    browser = PrimaryKeyRelatedField(queryset=Browser.objects.all())
    version = OptionalCharField(
        help_text='Version string.', allow_blank=False, max_length=20)
    release_day = DateField(
        help_text='Day of release to public, ISO 8601 format.',
        allow_null=True, required=False)
    retirement_day = DateField(
        help_text='Day this version stopped being supported, ISO 8601 format.',
        allow_null=True, required=False)
    status = ChoiceField(
        choices=[(choice, choice) for choice in (
            'unknown', 'current', 'future', 'retired', 'beta',
            'retired beta')],
        required=False)
    release_notes_uri = TranslatedTextField(
        help_text='URI of release notes.',
        allow_blank=True, allow_null=True, required=False,
        style={'base_template': 'textarea.html'})
    note = TranslatedTextField(
        help_text='Notes about this version.',
        allow_blank=True, allow_null=True,
        required=False, style={'base_template': 'textarea.html'})
    order = IntegerField(read_only=True, source='_order')
    supports = PrimaryKeyRelatedField(many=True, read_only=True)
    history = HistoryField(many=True, read_only=True)
    history_current = CurrentHistoryField(read_only=None)

    class Meta(BaseMeta):
        model = Version
        fields = OrderedDict((
            ('id', {}),
            ('browser', {
                'writable': 'at create',
                'archived': False}),
            ('version', {
                'writable': 'at create',
                'archived': False}),
            ('release_day', {}),
            ('retirement_day', {}),
            ('status', {}),
            ('release_notes_uri', {}),
            ('note', {}),
            ('order', {
                'archived': False}),
            ('supports', {
                'archived': False}),
            ('history_current', {
                'type': 'serializer field',
                'writable': 'at update',
                'archived': False}),
            ('history', {
                'type': 'many',
                'archived': False}),
        ))
        validators = [VersionAndStatusValidator()]


#
# Change control object serializers
#

class ChangesetSerializer(Serializer):
    """Changeset Serializer"""

    id = IntegerField(label='ID', read_only=True)
    created = DateTimeField(read_only=True)
    modified = DateTimeField(read_only=True)
    closed = BooleanField(
        help_text='Is the changeset closed to new changes?', required=False)
    target_resource_type = OptionalCharField(required=False)
    target_resource_id = OptionalIntegerField(required=False)
    user = PrimaryKeyRelatedField(
        default=CurrentUserDefault(), queryset=User.objects.all())
    historical_browsers = PrimaryKeyRelatedField(many=True, read_only=True)
    historical_features = PrimaryKeyRelatedField(many=True, read_only=True)
    historical_maturities = PrimaryKeyRelatedField(many=True, read_only=True)
    historical_sections = PrimaryKeyRelatedField(many=True, read_only=True)
    historical_specifications = PrimaryKeyRelatedField(
        many=True, read_only=True)
    historical_supports = PrimaryKeyRelatedField(many=True, read_only=True)
    historical_versions = PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta(BaseMeta):
        model = Changeset
        fields = OrderedDict((
            ('id', {}),
            ('created', {}),
            ('modified', {}),
            ('closed', {}),
            ('target_resource_type', {'writable': 'at create'}),
            ('target_resource_id', {'writeable': 'at create'}),
            ('user', {'writable': 'at create'}),
            ('historical_browsers', {}),
            ('historical_features', {}),
            ('historical_maturities', {}),
            ('historical_sections', {}),
            ('historical_specifications', {}),
            ('historical_supports', {}),
            ('historical_versions', {}),
        ))


class UserSerializer(Serializer):
    """User Serializer"""
    id = IntegerField(label='ID', read_only=True)
    username = OptionalCharField(
        help_text=(
            'Required. 30 characters or fewer. Letters, digits and @/./+/-/_'
            ' only.'),
        read_only=True)
    created = DateTimeField(read_only=True, source='date_joined')
    agreement = SerializerMethodField()
    permissions = SerializerMethodField()
    changesets = PrimaryKeyRelatedField(many=True, read_only=True)

    def get_agreement(self, obj):
        """What version of the contribution terms did the user agree to?

        Placeholder for when we have a license agreement.
        """
        return 0

    def get_permissions(self, obj):
        """Return names of django.contrib.auth Groups

        Can not be used with a writable view, since django.contrib.auth User
        doesn't have this method.  Will need updating or a proxy class.
        """
        assert hasattr(obj, 'group_names'), "Expecting cached User object"
        return obj.group_names

    class Meta(BaseMeta):
        model = User
        fields = OrderedDict((
            ('id', {}),
            ('username', {}),
            ('created', {}),
            ('agreement', {}),
            ('permissions', {}),
            ('changesets', {}),
        ))


#
# Historical object serializers
#


class ArchiveMixin(object):
    def get_fields(self):
        """Historical models don't quite follow Django model conventions."""
        fields = super(ArchiveMixin, self).get_fields()

        # Archived link fields are to-one relations
        for link_field in getattr(self.Meta, 'archive_link_fields', []):
            field = fields[link_field]
            field.source = (field.source or link_field) + '_id'

        return fields


class HistoricalObjectSerializer(Serializer):
    """Common serializer attributes for Historical models"""

    id = IntegerField(source="history_id")
    date = DateTimeField(source="history_date")
    event = SerializerMethodField()
    changeset = PrimaryKeyRelatedField(
        source="history_changeset", read_only=True)

    EVENT_CHOICES = {
        '+': 'created',
        '~': 'changed',
        '-': 'deleted',
    }

    def get_event(self, obj):
        return self.EVENT_CHOICES[obj.history_type]

    def get_archive(self, obj):
        serializer = self.ArchivedObject(obj)
        data = serializer.data
        data['id'] = str(data['id'])
        data['links'] = OrderedDict()

        # Archived link fields are to-one relations
        for field in getattr(serializer.Meta, 'archive_link_fields', []):
            del data[field]
            value = getattr(obj, field + '_id')
            if value is not None:
                value = str(value)
            data['links'][field] = value

        # Archived cached links fields are a list of primary keys
        for field in getattr(
                serializer.Meta, 'archive_cached_links_fields', []):
            value = getattr(obj, field)
            value = [str(x) for x in value]
            data['links'][field] = value
        data['links']['history_current'] = str(obj.history_id)

        return data

    class Meta(BaseMeta):
        fields = OrderedDict((
            ('id', {}),
            ('date', {}),
            ('event', {}),
            ('changeset', {}),
        ))


class HistoricalBrowserSerializer(HistoricalObjectSerializer):

    class ArchivedObject(BrowserSerializer):
        class Meta(BrowserSerializer.Meta):
            omit_fields = ['history_current', 'history', 'versions']

    browser = HistoricalObjectField()
    browsers = SerializerMethodField('get_archive')

    class Meta(HistoricalObjectSerializer.Meta):
        model = Browser.history.model
        fields = HistoricalObjectSerializer.Meta.fields.copy()
        fields.update(OrderedDict((
            ('browser', {}),
            ('browsers', {}),
        )))


class HistoricalFeatureSerializer(HistoricalObjectSerializer):

    class ArchivedObject(ArchiveMixin, FeatureSerializer):
        class Meta(FeatureSerializer.Meta):
            omit_fields = (
                'history_current', 'history', 'sections', 'supports',
                'children', 'url')
            archive_link_fields = ('parent',)
            archive_cached_links_fields = ('sections',)

    feature = HistoricalObjectField()
    features = SerializerMethodField('get_archive')

    class Meta(HistoricalObjectSerializer.Meta):
        model = Feature.history.model
        fields = HistoricalObjectSerializer.Meta.fields.copy()
        fields.update(OrderedDict((
            ('feature', {}),
            ('features', {}),
        )))


class HistoricalMaturitySerializer(HistoricalObjectSerializer):

    class ArchivedObject(ArchiveMixin, MaturitySerializer):
        class Meta(MaturitySerializer.Meta):
            omit_fields = ('specifications', 'history_current', 'history')

    maturity = HistoricalObjectField()
    maturities = SerializerMethodField('get_archive')

    class Meta(HistoricalObjectSerializer.Meta):
        model = Maturity.history.model
        fields = HistoricalObjectSerializer.Meta.fields.copy()
        fields.update(OrderedDict((
            ('maturity', {}),
            ('maturities', {}),
        )))


class HistoricalSectionSerializer(HistoricalObjectSerializer):

    class ArchivedObject(ArchiveMixin, SectionSerializer):
        class Meta(SectionSerializer.Meta):
            omit_fields = ('features', 'history_current', 'history')
            archive_link_fields = ('specification',)

    section = HistoricalObjectField()
    sections = SerializerMethodField('get_archive')

    class Meta(HistoricalObjectSerializer.Meta):
        model = Section.history.model
        fields = HistoricalObjectSerializer.Meta.fields.copy()
        fields.update(OrderedDict((
            ('section', {}),
            ('sections', {}),
        )))


class HistoricalSpecificationSerializer(HistoricalObjectSerializer):

    class ArchivedObject(ArchiveMixin, SpecificationSerializer):
        class Meta(SpecificationSerializer.Meta):
            omit_fields = ('sections', 'history_current', 'history')
            archive_link_fields = ('maturity',)

    specification = HistoricalObjectField()
    specifications = SerializerMethodField('get_archive')

    class Meta(HistoricalObjectSerializer.Meta):
        model = Specification.history.model
        fields = HistoricalObjectSerializer.Meta.fields.copy()
        fields.update(OrderedDict((
            ('specification', {}),
            ('specifications', {}),
        )))


class HistoricalSupportSerializer(HistoricalObjectSerializer):

    class ArchivedObject(ArchiveMixin, SupportSerializer):
        class Meta(SupportSerializer.Meta):
            omit_fields = ('history_current', 'history')
            archive_link_fields = ('version', 'feature')

    support = HistoricalObjectField()
    supports = SerializerMethodField('get_archive')

    class Meta(HistoricalObjectSerializer.Meta):
        model = Support.history.model
        fields = HistoricalObjectSerializer.Meta.fields.copy()
        fields.update(OrderedDict((
            ('support', {}),
            ('supports', {}),
        )))


class HistoricalVersionSerializer(HistoricalObjectSerializer):

    class ArchivedObject(ArchiveMixin, VersionSerializer):
        class Meta(VersionSerializer.Meta):
            omit_fields = ('supports', 'history_current', 'history')
            archive_link_fields = ('browser',)

    version = HistoricalObjectField()
    versions = SerializerMethodField('get_archive')

    class Meta(BaseMeta):
        model = Version.history.model
        fields = HistoricalObjectSerializer.Meta.fields.copy()
        fields.update(OrderedDict((
            ('version', {}),
            ('versions', {}),
        )))
