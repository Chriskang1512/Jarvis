"""Google Contacts read-only provider built on Google common components."""

from time import perf_counter

from jarvis.abilities.native.contacts.result import ContactResult
from jarvis.debug_trace import trace_event
from jarvis.privacy import redact_sensitive_text
from jarvis.providers.google.config import GOOGLE_CONTACTS_SCOPE, GoogleProviderConfig
from jarvis.providers.google.contacts.mapper import GoogleContactsMapper
from jarvis.providers.google.context import GoogleProviderContext
from jarvis.providers.google.errors import AUTH_REQUIRED, GoogleProviderError, google_error_message


READ_MASK = "names,emailAddresses,phoneNumbers,birthdays,metadata"


class GoogleContactsProvider:
    """Read contacts from Google People API."""

    provider_name = "google_contacts"

    def __init__(self, client=None, mapper=None, config=None, context=None):
        """Create provider with optional fake client for tests."""
        config = config or GoogleProviderConfig(scopes=(GOOGLE_CONTACTS_SCOPE,))
        self.context = context or GoogleProviderContext.create(config=config)
        self.config = self.context.config
        self.client = client
        self.client_factory = self.context.client_factory
        self.request_executor = self.context.request_executor
        self.error_mapper = self.context.error_mapper
        self.mapper = mapper or GoogleContactsMapper()

    def get_contact(self, query):
        """Search Google Contacts for one query."""
        started = perf_counter()
        search_text = str(getattr(query, "display_name", "") or getattr(query, "contact_id", "") or "").strip()
        trace_event("google_contacts.request", action="search", provider=self.provider_name, query=redact_sensitive_text(search_text))

        if search_text == "":
            return ContactResult(
                success=False,
                action="get",
                provider=self.provider_name,
                error_code="contact_not_found",
                execution_time_ms=elapsed_ms(started),
            )

        try:
            service = self.google_people_client()
            response = self.execute_google_request(
                lambda: service.people().searchContacts(query=search_text, readMask=READ_MASK, pageSize=10)
            )
            contacts = self.mapper.list_to_contacts(response)
            search_fetched = len(contacts)
            fallback_fetched = 0
            contact = best_contact_match(contacts, search_text)
            candidate_contacts = contacts

            if contact is None:
                fallback_contacts = self.fetch_connection_contacts(service, page_size=1000)
                fallback_fetched = len(fallback_contacts)
                candidate_contacts = dedupe_contacts((*contacts, *fallback_contacts))
                fallback_contact = best_contact_match(fallback_contacts, search_text)

                if fallback_contact is not None:
                    contacts = (fallback_contact,)
                    contact = fallback_contact

            ambiguous_contacts = ()

            if contact is None:
                ambiguous_contacts = partial_contact_matches(candidate_contacts, search_text)

            trace_event(
                "google_contacts.response",
                search_fetched=search_fetched,
                fallback_fetched=fallback_fetched,
                contacts=len(contacts),
                matched=1 if contact is not None else 0,
                ambiguous=len(ambiguous_contacts),
                provider=self.provider_name,
            )

            if contact is None and ambiguous_contacts:
                return ContactResult(
                    success=False,
                    action="get",
                    contacts=ambiguous_contacts,
                    changed_fields=(str(getattr(query, "attribute", "") or "contact"),),
                    provider=self.provider_name,
                    error_code="contact_ambiguous",
                    message=ambiguous_contact_message(search_text, ambiguous_contacts),
                    execution_time_ms=elapsed_ms(started),
                )

            return ContactResult(
                success=contact is not None,
                action="get",
                contact=contact,
                contacts=contacts if contact is not None else (),
                changed_fields=(str(getattr(query, "attribute", "") or "contact"),),
                revision=getattr(contact, "revision", 0) if contact is not None else 0,
                provider=self.provider_name,
                external_id=contact_external_id(contact),
                error_code="" if contact is not None else "contact_not_found",
                execution_time_ms=elapsed_ms(started),
            )
        except GoogleProviderError as error:
            return self.error_result("get", error, started)
        except Exception as error:
            return self.error_result("get", self.error_mapper.map_exception(error), started)

    def list_contacts(self, query=None):
        """Return a small page of Google contacts."""
        started = perf_counter()
        trace_event("google_contacts.request", action="list", provider=self.provider_name)

        try:
            service = self.google_people_client()
            contacts = self.fetch_connection_contacts(service, page_size=int(getattr(query, "limit", 10) or 10), max_pages=1)
            trace_event("google_contacts.response", contacts=len(contacts), provider=self.provider_name)
            return ContactResult(
                success=True,
                action="list",
                contacts=contacts,
                provider=self.provider_name,
                execution_time_ms=elapsed_ms(started),
            )
        except GoogleProviderError as error:
            return self.error_result("list", error, started)
        except Exception as error:
            return self.error_result("list", self.error_mapper.map_exception(error), started)

    def create_contact(self, query):
        """Create one Google contact."""
        started = perf_counter()
        display_name = str(getattr(query, "display_name", "") or "").strip()
        trace_event("google_contacts.request", action="create", provider=self.provider_name, query=redact_sensitive_text(display_name))

        if not display_name:
            return ContactResult(
                success=False,
                action="create",
                provider=self.provider_name,
                error_code="display_name_required",
                execution_time_ms=elapsed_ms(started),
            )

        try:
            service = self.google_people_client()
            body = build_google_contact_body(query)
            response = self.execute_google_request(lambda: service.people().createContact(body=body))
            contact = self.mapper.to_contact(response)
            trace_event("google_contacts.response", contacts=1, provider=self.provider_name)
            return ContactResult(
                success=True,
                action="create",
                contact=contact,
                contacts=(contact,),
                changed_fields=query_changed_fields(query, default=("display_name",)),
                revision=getattr(contact, "revision", 0),
                provider=self.provider_name,
                external_id=contact_external_id(contact),
                execution_time_ms=elapsed_ms(started),
            )
        except GoogleProviderError as error:
            return self.error_result("create", error, started)
        except Exception as error:
            return self.error_result("create", self.error_mapper.map_exception(error), started)

    def update_contact(self, query):
        """Update one Google contact by provider resourceName only."""
        started = perf_counter()
        display_name = str(getattr(query, "display_name", "") or getattr(query, "contact_id", "") or "").strip()
        trace_event("google_contacts.request", action="update", provider=self.provider_name, query=redact_sensitive_text(display_name))

        changed_fields = query_changed_fields(query)
        if not changed_fields:
            return ContactResult(
                success=False,
                action="update",
                provider=self.provider_name,
                error_code="no_update_fields",
                execution_time_ms=elapsed_ms(started),
            )

        try:
            service = self.google_people_client()
            resource_name = contact_query_external_id(query)

            if not resource_name:
                resolved = self.get_contact(query)
                if not resolved.success:
                    return ContactResult(
                        success=False,
                        action="update",
                        contacts=tuple(getattr(resolved, "contacts", ()) or ()),
                        changed_fields=changed_fields,
                        provider=self.provider_name,
                        error_code=resolved.error_code or "contact_not_found",
                        message=resolved.message,
                        execution_time_ms=elapsed_ms(started),
                    )
                resource_name = contact_external_id(resolved.contact)

            if not is_google_resource_name(resource_name):
                return ContactResult(
                    success=False,
                    action="update",
                    provider=self.provider_name,
                    error_code="resource_name_required",
                    message="Google Contacts update requires a people/... resourceName.",
                    execution_time_ms=elapsed_ms(started),
                )

            existing = self.execute_google_request(
                lambda: service.people().get(resourceName=resource_name, personFields=READ_MASK)
            )
            body = merge_google_contact_body(existing, query)
            update_fields = google_update_person_fields(changed_fields)
            response = self.execute_google_request(
                lambda: service.people().updateContact(
                    resourceName=resource_name,
                    updatePersonFields=update_fields,
                    body=body,
                )
            )
            contact = self.mapper.to_contact(response)
            trace_event("google_contacts.response", contacts=1, provider=self.provider_name)
            return ContactResult(
                success=True,
                action="update",
                contact=contact,
                contacts=(contact,),
                changed_fields=changed_fields,
                revision=getattr(contact, "revision", 0),
                provider=self.provider_name,
                external_id=contact_external_id(contact),
                execution_time_ms=elapsed_ms(started),
            )
        except GoogleProviderError as error:
            return self.error_result("update", error, started)
        except Exception as error:
            return self.error_result("update", self.error_mapper.map_exception(error), started)

    def google_people_client(self):
        """Return a Google People API client."""
        return self.client or self.client_factory.people_client()

    def execute_google_request(self, request_factory):
        """Execute one Google request through the shared executor."""
        result = self.request_executor.execute(request_factory)

        if result.success:
            return result.response

        raise result.error

    def fetch_connection_contacts(self, service, page_size=100, max_pages=5):
        """Fetch Google connections and map them to contacts."""
        contacts = []
        page_token = ""
        pages = 0

        while pages < int(max_pages or 1):
            pages += 1
            response = self.execute_google_request(
                lambda token=page_token: service.people().connections().list(
                    resourceName="people/me",
                    personFields=READ_MASK,
                    pageSize=int(page_size or 100),
                    pageToken=token or None,
                )
            )
            contacts.extend(self.mapper.list_to_contacts(response))
            page_token = str(dict(response or {}).get("nextPageToken") or "")

            if not page_token:
                break

        return tuple(contacts)

    def error_result(self, action, error, started):
        """Return a safe ContactResult for provider errors."""
        code = getattr(error, "code", AUTH_REQUIRED)
        return ContactResult(
            success=False,
            action=action,
            provider=self.provider_name,
            error_code=code,
            message=getattr(error, "safe_message", "") or google_error_message(code),
            execution_time_ms=elapsed_ms(started),
        )


def contact_external_id(contact):
    """Return provider-native external ID for a contact."""
    metadata = dict(getattr(contact, "metadata", {}) or {})
    return str(metadata.get("external_id") or metadata.get("google_resource_name") or "")


def create_google_contacts_provider(config=None, client=None):
    """Create Google Contacts provider."""
    config = config or GoogleProviderConfig(scopes=(GOOGLE_CONTACTS_SCOPE,))
    return GoogleContactsProvider(config=config, client=client)


def contact_query_external_id(query):
    """Return a Google resourceName from a ContactQuery when present."""
    external_id = str(getattr(query, "external_id", "") or "").strip()
    contact_id = str(getattr(query, "contact_id", "") or "").strip()

    if external_id:
        return external_id
    if contact_id.startswith("people/"):
        return contact_id
    return ""


def is_google_resource_name(value):
    """Return whether value is a Google People API resourceName."""
    return str(value or "").startswith("people/")


def build_google_contact_body(query):
    """Build a minimal People API contact body from a ContactQuery."""
    body = {}
    display_name = str(getattr(query, "display_name", "") or "").strip()

    if display_name:
        body["names"] = [{"givenName": display_name, "displayName": display_name}]
    if getattr(query, "email", ""):
        body["emailAddresses"] = [{"value": str(query.email)}]
    if getattr(query, "phone", ""):
        body["phoneNumbers"] = [{"value": str(query.phone)}]
    if getattr(query, "birthday", ""):
        body["birthdays"] = [{"date": google_birthday_date(query.birthday)}]

    return body


def merge_google_contact_body(existing, query):
    """Return an update body preserving Google metadata while replacing requested fields."""
    body = dict(existing or {})

    if getattr(query, "display_name", "") and not body.get("names"):
        body["names"] = [{"givenName": str(query.display_name), "displayName": str(query.display_name)}]
    if getattr(query, "email", ""):
        body["emailAddresses"] = [{"value": str(query.email)}]
    if getattr(query, "phone", ""):
        body["phoneNumbers"] = [{"value": str(query.phone)}]
    if getattr(query, "birthday", ""):
        body["birthdays"] = [{"date": google_birthday_date(query.birthday)}]

    return body


def google_birthday_date(value):
    """Return a People API date dictionary from MM-DD or YYYY-MM-DD."""
    text = str(value or "").strip()
    parts = text.split("-")

    if len(parts) == 3:
        return {"year": int(parts[0]), "month": int(parts[1]), "day": int(parts[2])}
    if len(parts) == 2:
        return {"month": int(parts[0]), "day": int(parts[1])}

    return {}


def query_changed_fields(query, default=()):
    """Return changed fields for one contact write query."""
    fields = []

    if getattr(query, "display_name", "") and default:
        fields.extend(default)
    if getattr(query, "email", ""):
        fields.append("emails")
    if getattr(query, "phone", ""):
        fields.append("phones")
    if getattr(query, "birthday", ""):
        fields.append("birthday")
    if getattr(query, "aliases", ()):
        fields.append("aliases")

    return tuple(fields)


def google_update_person_fields(changed_fields):
    """Return People API updatePersonFields from ContactResult changed fields."""
    fields = set(changed_fields or ())
    google_fields = []

    if fields & {"display_name", "names"}:
        google_fields.append("names")
    if fields & {"emails", "email"}:
        google_fields.append("emailAddresses")
    if fields & {"phones", "phone"}:
        google_fields.append("phoneNumbers")
    if "birthday" in fields:
        google_fields.append("birthdays")

    return ",".join(google_fields)


def best_contact_match(contacts, search_text):
    """Return a safe contact match without trusting provider ordering."""
    normalized = normalize_match_text(search_text)

    for contact in contacts or ():
        candidates = [getattr(contact, "display_name", ""), *list(getattr(contact, "aliases", ()) or ())]
        if any(normalize_match_text(candidate) == normalized for candidate in candidates):
            return contact

    token_matches = []

    for contact in contacts or ():
        candidates = [getattr(contact, "display_name", ""), *list(getattr(contact, "aliases", ()) or ())]
        if any(normalized in normalize_match_tokens(candidate) for candidate in candidates):
            token_matches.append(contact)

    if len(token_matches) == 1:
        return token_matches[0]

    return None


def partial_contact_matches(contacts, search_text):
    """Return partial-name candidates that require user clarification."""
    normalized = normalize_match_text(search_text)

    if normalized == "":
        return ()

    matches = []

    for contact in contacts or ():
        candidates = [getattr(contact, "display_name", ""), *list(getattr(contact, "aliases", ()) or ())]

        if any(is_partial_name_match(normalized, candidate) for candidate in candidates):
            matches.append(contact)

    return dedupe_contacts(matches)


def is_partial_name_match(normalized_query, candidate):
    """Return whether the query is a partial candidate, not an exact safe match."""
    normalized_candidate = normalize_match_text(candidate)

    if normalized_candidate == "" or normalized_query == normalized_candidate:
        return False

    if normalized_query in normalize_match_tokens(candidate):
        return False

    return normalized_query in normalized_candidate


def dedupe_contacts(contacts):
    """Return contacts without duplicate provider IDs or display names."""
    deduped = []
    seen = set()

    for contact in contacts or ():
        key = contact_external_id(contact) or getattr(contact, "id", "") or normalize_match_text(getattr(contact, "display_name", ""))

        if key in seen:
            continue

        seen.add(key)
        deduped.append(contact)

    return tuple(deduped)


def ambiguous_contact_message(search_text, contacts):
    """Return a safe clarification message for partial contact matches."""
    names = [str(getattr(contact, "display_name", "") or "").strip() for contact in contacts or ()]
    names = [name for name in names if name]

    if len(names) == 1:
        return f"'{search_text}'와 정확히 일치하는 연락처는 없습니다. '{names[0]}'를 말씀하신 건가요?"

    preview = ", ".join(names[:3])

    if len(names) > 3:
        preview = f"{preview} 외 {len(names) - 3}명"

    return f"'{search_text}'와 정확히 일치하는 연락처는 없습니다. 비슷한 연락처가 {len(names)}개 있습니다: {preview}. 누구를 찾을까요?"


def normalize_match_text(value):
    """Normalize text for loose contact matching."""
    return "".join(str(value or "").lower().split())


def normalize_match_tokens(value):
    """Return normalized name tokens for safer contact matching."""
    return tuple(token for token in re_split_name_tokens(str(value or "")) if token)


def re_split_name_tokens(value):
    """Split display names into comparable tokens."""
    import re

    return [normalize_match_text(token) for token in re.split(r"[\s,;/|()\[\]{}<>·ㆍ\-]+", value)]


def elapsed_ms(started):
    """Return elapsed ms."""
    return int((perf_counter() - started) * 1000)
