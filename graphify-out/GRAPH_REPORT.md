# Graph Report - TimetableManagement  (2026-11-09)

## Corpus Check
- 490 files · ~418,961 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 17 file(s) not represented in the graph (top: .service 3, (none) 2, .conf 2)

## Summary
- 7766 nodes · 23416 edges · 277 communities (222 shown, 55 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 1210 edges (avg confidence: 0.87)
- Token cost: 84 input · 1,180 output

## Community Hubs (Navigation)
- Attendance Page
- Use Set Page Header
- App
- Slot
- Audit Tables
- Hub
- Data Access Teacher Portal
- Access
- Permission Denied
- Admin Faculty
- Registry
- Handle
- Account Page
- Faculty Api
- Bookings Page
- Health Check
- Admin Shifts
- Admin Cli
- Data Access Users
- Data Access Webhooks
- Confirmation Option
- English Weekday When Value
- Allowed
- Courses
- Attendance Calc
- Apply Login
- Factory
- Data Access Proxy Log
- Period Statistics
- Availability
- Services Exams
- MYSQL Rebuilt Once Upgrade
- Page Access
- User
- Data Access Lecture Sessions
- Core Capabilities
- Data Access User Actions
- Unauthenticated Reads
- Create App
- Data Access Mobile Devices
- Integrations
- Close
- Faculty Sync
- Handle
- Account
- Introspect
- Timetable Page
- After Request
- Baseline
- Cryptography Exceptions
- Flask Wtf
- Csp
- Mark Refused
- Holidays For Range
- Operations
- Status
- Dashboard
- App Factory
- Data Access Lab Batches
- Security
- Students Api
- Share One Fixed Window
- Face
- Body
- Consent Payload
- Binascii
- Factories
- Pdf Response
- Data Access Student Portal
- Rules
- Cohort Key
- Student Sync
- Testing
- Response Envelope
- Export Jobs
- Data Access Invitations
- Fetch Permissions With Description
- Active
- Persist Cohort
- Minutes
- Admin
- Data Access Profile
- Production Requirements
- Timetable
- Counts Attended
- Bulk Set Day Availability
- Get Connection
- Role Permissions
- Catalog Assessment
- Create App
- Seeders Base
- Data Permissions
- Timetable Services
- Util
- Holidays For Week
- User Access
- Reports Admin Common
- Get User Accessible Departments
- Calendar
- Faculty Attendance Page
- Clashes
- Settings
- Sharing Input
- Admin Timetable
- Audit Cli
- Clean Preferences
- Versions
- Change User
- Timetable Features
- Build Scope
- Fetch Allocated Faculty
- Availability Absence Copies
- Courses Api
- Assign Rooms
- Account GET Api Session
- Cohort Slots Clash
- Reports
- Timetable Versions
- Departments Api
- Sign Student Teacher Redirect
- Booking When
- Create User
- Institution Input
- Exceptions
- Shifts
- Insert Processed Absence
- Error
- Test Admin Login
- Catalog Exams
- Process Wide Registry For
- Generator
- Test Remaining Extracts
- Data Access Attendance Calc
- Count Active Sessions
- Sessions
- Services Notifications
- Test Registration
- App Errorhandler
- Check Maintenance Mode
- Test Notifications
- Proxy
- Test Active Config
- Academic Term
- Tsconfig App
- 0009 Worker Claims
- Queue Test Message
- Build
- Hhmm
- Deactivate User
- Test Uploads Transaction
- Delete Faculty Availability
- Account Authority
- Open Lab Batch Audit
- Tenant Connection Settings
- Tsconfig Node
- College Timetable
- Authority
- Black Background
- Cohort Names
- Test Face Safeguards
- Test Admin Portal Extract
- Test Profile
- When Tenant Has One
- Fetch Departments
- Record Logout Deactivate That
- Deactivate Session
- Renderers
- Find User
- Query
- 0001 Baseline Existing Schema
- Request
- Data Access Audit Logs
- Services
- Busy Clause
- Delete Rows
- Test Permission Matrix
- Test Split Connection Locks
- Test Admin Screen Extract
- Cryptography Fernet
- Schema Ownership
- Notification Settings Page
- Concurrency
- TFLite Face Pipeline
- Notifications Off
- Format Time Filter
- Teaching Day Scheduling Cancellation
- Default Avatar
- Util
- Audit
- Fetch Activity Summary
- Shared Job Claim Columns
- MYSQL CLIENT
- 0008 Attendance Views
- Isolation
- 0016 Timetable Preferences
- 0019 Academic Calendar
- Test Timetable Grid
- Test Error Pages
- Face Embedding
- MARIADB PASSWORD
- Script
- Test Academic Calendar
- Attendance Calculation Service
- Attendance Admin Common
- Data Access Roles
- Runs
- 0003 Security Schema
- 0007 Lecture Sessions
- 0012 Lab Batches
- 0017 Timetable Versions
- 0018 Bookings
- 0020 Syllabus
- 0021 Assessment
- 0022 Exam Schedule
- After Close Day
- Cursor
- Tenant Organization Institution Department
- Runs
- Defaults
- 0006 Sign Lock
- Stored Score Document Version
- 0010 Face Safeguards
- 0011 Notifications
- 0013 Integrations
- 0016 Timetable Preferences
- Logger
- Needs
- Execute
- Test Replace Shares Only
- Ids Signed User May
- Test Database Guard
- Tsconfig
- Frame Hash
- Fetch Hourly Activity
- Fetch Most Active Users
- Count Permissions
- Count Roles
- Delete One Role Permission
- Delete Role Permissions For
- Fetch Assigned Permissions
- Fetch Common Permissions
- Fetch Existing Role Permission
- Fetch Permission Choices
- Fetch Permission Distribution
- Fetch Permission Names
- Fetch Permissions For Modules
- Fetch Role
- Fetch Role Description
- Fetch Role Permission Ids
- Fetch Role Record
- Fetch Role Usage
- Fetch Roles For Export
- Fetch Roles With Counts
- Fetch Users Role
- Fetch Users For Role
- Insert Role
- Insert Role Permission
- Insert Role Permission For
- Rename Role Replace Its
- Backup
- Install
- Restore

## God Nodes (most connected - your core abstractions)
1. `json_error()` - 320 edges
2. `json_ok()` - 292 edges
3. `safe_text()` - 271 edges
4. `safe_count()` - 250 edges
5. `InputError` - 232 edges
6. `safeText()` - 198 edges
7. `close()` - 185 edges
8. `login()` - 173 edges
9. `messageFrom()` - 172 edges
10. `reject_input()` - 165 edges

## Surprising Connections (you probably didn't know these)
- `test_times_overlap_uses_the_previous_boundaries()` --calls--> `times_overlap()`  [EXTRACTED]
  tests/unit/test_clashes.py → academic_rules/clashes.py
- `open_lecture_session()` --uses--> `SessionCancelled`  [INFERRED]
  api/mobile/v1/student_sync.py → services/lecture_sessions.py
- `_record_synced_lesson()` --uses--> `LessonRejected`  [INFERRED]
  api/mobile/v1/student_sync.py → services/syllabus.py
- `upload_attendance_logs()` --uses--> `LessonRejected`  [INFERRED]
  api/mobile/v1/student_sync.py → services/syllabus.py
- `test_proxy_filters_keep_the_old_allow_list()` --uses--> `InputError`  [INFERRED]
  tests/unit/test_admin_shift_pages.py → api/web/access.py

## Import Cycles
- 2-file cycle: `api/v1/__init__.py -> api/v1/routes.py -> api/v1/__init__.py`
- 2-file cycle: `api/mobile/v1/faculty_sync.py -> api/mobile/v1/sync_attendance.py -> api/mobile/v1/faculty_sync.py`
- 2-file cycle: `api/mobile/v1/student_sync.py -> api/mobile/v1/sync_attendance.py -> api/mobile/v1/student_sync.py`

## Hyperedges (group relationships)
- **Attendance percentage pipeline** — docs_design_attendance_calculation_in_roster, docs_design_attendance_calculation_lecture_sessions, docs_design_attendance_calculation_policy, docs_design_attendance_calculation_attendance_calc, docs_design_attendance_calculation_close_day [EXTRACTED 1.00]
- **Phase K optional academic features** — docs_design_capabilities_registry, docs_academics_academic_terms, docs_academics_syllabus, docs_academics_assessments, docs_academics_exams [EXTRACTED 1.00]
- **Transactional outbox with shared job claims** — docs_database_job_claims, docs_notifications_outbox, docs_integrations_webhooks [EXTRACTED 1.00]
- **Host to tenant database** — docs_tenancy_request_routing, docs_tenancy_tenant_registry, docs_tenancy_connection_settings, docs_tenancy_session_binding, docs_tenancy_tenant [EXTRACTED 1.00]
- **Timetable generation pipeline** — docs_timetable_generate_api, docs_timetable_timetable_jobs, docs_timetable_greedy_solver, docs_timetable_joint_solver, docs_timetable_quality_model, docs_timetable_rules_registry [EXTRACTED 1.00]
- **Room clash ledger** — docs_timetable_bookings, docs_timetable_check_slot, docs_timetable_manual_slots, docs_timetable_greedy_solver, docs_timetable_joint_solver [EXTRACTED 1.00]
- **Gray disc, head, and shoulders form the default avatar** — static_default_avatar_gray_disc, static_default_avatar_head, static_default_avatar_shoulders [EXTRACTED 1.00]
- **Background circle, head circle, and shoulder path form the default avatar** — static_default_avatar_background_circle, static_default_avatar_head_circle, static_default_avatar_shoulder_path [EXTRACTED 1.00]
- **Hooded figure** — static_favicon_blue_hoodie, static_favicon_shadowed_face, static_favicon_white_grin, static_favicon_closed_eyes, static_favicon_crossed_arms [EXTRACTED 1.00]
- **Tech backdrop** — static_favicon_wireframe_spheres, static_favicon_cyan_grid, static_favicon_black_background [EXTRACTED 1.00]
- **Favicon mark** — static_favicon_hooded_figure, static_favicon_wireframe_spheres, static_favicon_cyan_grid [EXTRACTED 1.00]

## Communities (277 total, 55 thin omitted)

### Community 0 - "Attendance Page"
Cohesion: 0.02
Nodes (183): AttendancePage(), AttendanceRecord, AttendanceRecordsPage(), save(), CANCEL_REASONS, Choice, emptyFigures, Figures (+175 more)

### Community 1 - "Use Set Page Header"
Cohesion: 0.04
Nodes (163): useSetPageHeader(), asId(), emptyPermissions, Option, optionsOf(), Permissions, permissionsOf(), readList() (+155 more)

### Community 2 - "App"
Cohesion: 0.04
Nodes (100): App(), exact, reactPath(), LegacyRedirect(), LegacyStaffAlias(), PrefixedRedirect(), AdminFrame(), AdminFrameProps (+92 more)

### Community 3 - "Slot"
Cohesion: 0.06
Nodes (98): _slot(), iso_date(), page_window(), _activity_row(), _session_row(), _date(), _denied(), _detail() (+90 more)

### Community 4 - "Audit Tables"
Cohesion: 0.04
Nodes (96): actionTone(), AuditFailedPage(), AuditLogsPage(), AuditSessionsPage(), failedColumns, FailedRow, logColumns, LogRow (+88 more)

### Community 5 - "Hub"
Cohesion: 0.04
Nodes (61): _change_denied(), _denied(), _listing(), _public_institution(), _public_organization(), register_institution_routes(), create_institution(), list_institutions() (+53 more)

### Community 6 - "Data Access Teacher Portal"
Cohesion: 0.04
Nodes (51): delete_faculty_absence(), delete_faculty_availability(), fetch_absence_rows(), fetch_absence_status(), fetch_assignments(), fetch_availability_slots(), fetch_class_students(), fetch_day_schedule() (+43 more)

### Community 7 - "Access"
Cohesion: 0.06
Nodes (70): as_date(), as_number(), decimal_number(), flag(), id_list(), InputError, optional_id(), optional_text() (+62 more)

### Community 8 - "Permission Denied"
Cohesion: 0.06
Nodes (78): permission_denied(), reject_input(), register_allocation_routes(), create_allocation(), delete_allocation(), update_allocation(), _course_in_scope(), _public() (+70 more)

### Community 9 - "Admin Faculty"
Cohesion: 0.04
Nodes (45): approve_proxy_log(), deactivate_faculty(), deactivate_faculty_users(), delete_absence(), fetch_absence_for_approval(), fetch_absence_status(), fetch_absences(), fetch_download_with_rooms() (+37 more)

### Community 10 - "Registry"
Cohesion: 0.08
Nodes (67): _envelope(), _flask_to_openapi(), openapi_document(), Operation, operation(), wrap(), academic_years(), BadParameter (+59 more)

### Community 11 - "Handle"
Cohesion: 0.06
Nodes (59): handle(), _import(), _import_rows(), work(), active(), allocated_subjects(), AssessmentError, attain() (+51 more)

### Community 12 - "Account Page"
Cohesion: 0.04
Nodes (69): AccountPage(), savePassword(), saveProfile(), FaceConsent, PortalProfilePage(), changeConsent(), savePassword(), saveProfile() (+61 more)

### Community 13 - "Faculty Api"
Cohesion: 0.07
Nodes (68): asId(), createFaculty(), deactivateFaculty(), emptyFacultyPermissions, FacultyDraft, FacultyList, FacultyOption, FacultyPermissions (+60 more)

### Community 14 - "Bookings Page"
Cohesion: 0.05
Nodes (66): Booking, BookingsPage(), cancel(), decide(), submit(), Draft, emptyDraft, kindLabel (+58 more)

### Community 15 - "Health Check"
Cohesion: 0.05
Nodes (34): health_check(), _database_problem(), _operational_checks(), retrain_quality_model_once(), _start_quality_model_retrainer(), retrain_loop(), tenant_context(), tenants_to_serve() (+26 more)

### Community 16 - "Admin Shifts"
Cohesion: 0.05
Nodes (34): count_active_shifts(), count_faculty_with_shifts(), count_shift_usage(), delete_shift_pattern(), fetch_active_departments(), fetch_active_faculty(), fetch_active_patterns(), fetch_active_shift_choices() (+26 more)

### Community 17 - "Admin Cli"
Cohesion: 0.07
Nodes (27): _audit(), create_superadmin(), create_superadmin_account(), _password(), backfill_command(), close_day_command(), _connection(), _date() (+19 more)

### Community 18 - "Data Access Users"
Cohesion: 0.05
Nodes (37): deactivate_faculty(), deactivate_students(), fetch_course_department_id(), fetch_default_course_id(), fetch_default_department_id(), fetch_faculty_contact(), fetch_faculty_profile(), fetch_first_course_for_department() (+29 more)

### Community 19 - "Data Access Webhooks"
Cohesion: 0.05
Nodes (45): delete_endpoint(), fetch_delivery(), fetch_endpoint(), fetch_endpoints(), insert_delivery(), insert_endpoint(), mark_retry(), mark_sent() (+37 more)

### Community 20 - "Confirmation Option"
Cohesion: 0.07
Nodes (36): _create_database(), _database_exists(), _refuse_in_tests(), _registry(), _settings_for(), _stamp(), tenant_create(), tenant_forget() (+28 more)

### Community 21 - "English Weekday When Value"
Cohesion: 0.06
Nodes (33): weekday_name(), fetch_students(), fetch_session_for(), count_attendance_for_date(), fetch_attendance_history(), fetch_existing_attendance(), fetch_faculty_table_id(), fetch_history_lecture() (+25 more)

### Community 22 - "Allowed"
Cohesion: 0.08
Nodes (52): allowed(), _change_denied(), _list(), _payload(), register_capability_routes(), _save(), _view_denied(), _coverage() (+44 more)

### Community 23 - "Courses"
Cohesion: 0.08
Nodes (50): _active(), _can(), _close(), _code(), _CourseInputError, _department_id(), _input_error(), _optional_text() (+42 more)

### Community 24 - "Attendance Calc"
Cohesion: 0.10
Nodes (40): can_still_reach(), _check(), classes_needed(), classes_that_can_be_missed(), _fraction(), meets(), classify(), countable_sessions() (+32 more)

### Community 25 - "Apply Login"
Cohesion: 0.06
Nodes (33): apply_at_login(), deactivate_user_session(), fetch_admin_login_user(), fetch_faculty_links(), fetch_login_user(), fetch_student_links(), fetch_user_profile(), insert_user_session() (+25 more)

### Community 26 - "Factory"
Cohesion: 0.08
Nodes (32): Factory, test_faculty_timetable_free_can_ignore_inactive_rows(), cohort(), d(), lesson(), test_factories_build_every_role_with_linked_rows(), test_isolation_restores_changed_tables(), _admin() (+24 more)

### Community 27 - "Data Access Proxy Log"
Cohesion: 0.06
Nodes (26): approve_mapped_proxy(), fetch_cover_faculty(), fetch_named_faculty(), fetch_proxy_clash(), fetch_proxy_request(), fetch_proxy_summary(), reject_pending_proxy(), _covers() (+18 more)

### Community 28 - "Period Statistics"
Cohesion: 0.08
Nodes (49): period_statistics(), login(), by_name(), MarchDay, my_attendance(), payload(), test_asha_sees_held_lectures_and_pooled_totals(), test_ben_counts_the_elective_and_sees_physics_without_a_figure() (+41 more)

### Community 29 - "Availability"
Cohesion: 0.06
Nodes (30): faculty_is_available(), manual_add_availability_block(), _applies(), _field(), is_working_day(), recurring_holiday_blocks_day(), recurring_holiday_taken(), weekday_number() (+22 more)

### Community 30 - "Services Exams"
Cohesion: 0.08
Nodes (45): _allows(), _as_date(), _as_time(), _covers(), create_exam(), _dates(), delete_exam(), _elective() (+37 more)

### Community 31 - "MYSQL Rebuilt Once Upgrade"
Cohesion: 0.09
Nodes (34): test_database(), checked_name(), configured_database(), credentials(), database_connection(), drop(), migrate(), recreate() (+26 more)

### Community 32 - "Page Access"
Cohesion: 0.07
Nodes (51): AccessSession, canOpenPage(), canOpenStaffHome(), deviceRoles, hasPermission(), linkVisible(), PagePermission, pagePermission (+43 more)

### Community 33 - "User"
Cohesion: 0.10
Nodes (47): test_reports_api_offers_the_accreditation_types_and_formats(), _assert_refused(), _assert_signed_in(), test_a_locked_account_is_refused_with_the_right_password(), test_admin_form_refuses_a_wrong_password(), test_admin_form_signs_in(), test_admin_roles_are_refused_on_the_login_form(), test_an_inactive_account_is_refused() (+39 more)

### Community 34 - "Data Access Lecture Sessions"
Cohesion: 0.06
Nodes (27): count_marks(), delete_marks(), fetch_active_slots_for_weekday(), fetch_approved_proxy(), fetch_marked_student_ids(), fetch_mobile_sessions_for_date(), fetch_proxies_for_date(), fetch_session() (+19 more)

### Community 35 - "Core Capabilities"
Cohesion: 0.07
Nodes (30): _cache(), Capability, clean_setting(), clean_settings(), describe(), enabled(), flag_name(), flag_on() (+22 more)

### Community 36 - "Data Access User Actions"
Cohesion: 0.07
Nodes (25): fetch_activity_for_export(), fetch_bulk_targets(), fetch_user_role(), fetch_user_status(), fetch_users_for_export(), update_bulk_faculty_active(), update_bulk_passwords(), update_bulk_student_active() (+17 more)

### Community 37 - "Unauthenticated Reads"
Cohesion: 0.07
Nodes (52): Unauthenticated JSON reads, Mobile sync blueprint, Account API, Attendance API, Audit API, auth blueprint, Bookings API, Branding API (+44 more)

### Community 38 - "Create App"
Cohesion: 0.05
Nodes (25): create_app(), has_user_permission(), track_session_activity(), TestingConfig, configure_migrations(), _install_migration_context_defaults(), session_activity_tracker(), app() (+17 more)

### Community 39 - "Data Access Mobile Devices"
Cohesion: 0.07
Nodes (23): fetch_active_users(), fetch_device_active(), fetch_device_id(), fetch_mobile_devices(), insert_mobile_device(), update_device_active(), update_device_secret(), create_mobile_device() (+15 more)

### Community 40 - "Integrations"
Cohesion: 0.13
Nodes (45): _change_denied(), _create_key(), work(), _create_webhook(), work(), _delete_webhook(), work(), _deliveries() (+37 more)

### Community 41 - "Close"
Cohesion: 0.08
Nodes (39): close(), _activity_page(), _activity_size(), _cancel(), cancel_by_date(), _cancel_payload(), cancel_session(), _choice_id() (+31 more)

### Community 42 - "Faculty Sync"
Cohesion: 0.10
Nodes (37): reprocess_failed_faculty_logs(), resolve_faculty_shift_session(), upload_faculty_attendance_logs(), resolve_timetable_session(), sync_timetable(), _build_custom_shift_key(), _build_photo_url(), _column_exists() (+29 more)

### Community 43 - "Handle"
Cohesion: 0.09
Nodes (31): handle(), accept_lesson(), active(), clean_lesson(), clean_units(), coverage_for(), coverage_lines(), _decimal() (+23 more)

### Community 44 - "Account"
Cohesion: 0.08
Nodes (29): _date_text(), _face_consent(), _face_consent_give(), _face_consent_withdraw(), _fields(), _kept(), _password(), _profile_payload() (+21 more)

### Community 45 - "Introspect"
Cohesion: 0.08
Nodes (27): compare(), _describe(), _first_difference(), _ignored(), missing_fk_targets(), read_schema(), _rows(), server_version() (+19 more)

### Community 46 - "Timetable Page"
Cohesion: 0.07
Nodes (46): Candidate, cellKey(), cellLabel(), checkFrom(), emptySlot, GeneratePage(), generate(), Generation (+38 more)

### Community 47 - "After Request"
Cohesion: 0.07
Nodes (26): authenticate_key(), _bearer(), _rate_limited(), security_headers(), fetch_by_prefix(), fetch_key(), fetch_keys(), insert_key() (+18 more)

### Community 48 - "Baseline"
Cohesion: 0.09
Nodes (27): baseline_objects(), baseline_statements(), check_repairs(), clean_dump(), invoker_view(), main(), _repair_table(), server_version_of() (+19 more)

### Community 49 - "Cryptography Exceptions"
Cohesion: 0.08
Nodes (29): delete_identity(), fetch_identities(), fetch_identity(), fetch_settings(), fetch_staff_user_by_email(), fetch_user(), insert_identity(), table_exists() (+21 more)

### Community 50 - "Flask Wtf"
Cohesion: 0.07
Nodes (25): get_db(), admin_login(), home(), login(), logout(), register(), sso_callback(), _sso_failed() (+17 more)

### Community 51 - "Csp"
Cohesion: 0.06
Nodes (41): HeaderMode, securityHeaders(), dependencies, react@^19.3.1, react-dom@^19.3.1, react-router-dom@^7.18.4, devDependencies, tailwindcss@^4.3.3 (+33 more)

### Community 52 - "Mark Refused"
Cohesion: 0.11
Nodes (37): MarkRefused, close_day(), _approve_proxy(), audit(), cancel(), lecture_day(), lesson(), mark() (+29 more)

### Community 53 - "Holidays For Range"
Cohesion: 0.09
Nodes (27): holidays_for_range(), active(), _as_date(), clean_term(), configured(), delete_term(), _institution_of_slot(), kept_dates() (+19 more)

### Community 54 - "Operations"
Cohesion: 0.07
Nodes (23): operations(), _email_allowed(), _app(), _b64url(), _Bind, _claims(), _delivery(), _DeliveryConnection (+15 more)

### Community 55 - "Status"
Cohesion: 0.08
Nodes (28): head_revision(), reason_for(), _revisions(), revisions_from(), stamped(), app(), client(), _data() (+20 more)

### Community 56 - "Dashboard"
Cohesion: 0.07
Nodes (24): clip_trend(), _empty_report(), _hours(), _percent(), register_dashboard_routes(), dashboard_summary(), count(), _report() (+16 more)

### Community 57 - "App Factory"
Cohesion: 0.09
Nodes (17): _configure_logging(), format_time_12hr_filter(), alert_handler_from_config(), AlertHandler, ContextFilter, current_request_id(), _incoming_request_id(), install_request_ids() (+9 more)

### Community 58 - "Data Access Lab Batches"
Cohesion: 0.08
Nodes (24): add_membership(), delete_group(), end_membership(), fetch_cohort_students(), fetch_current_memberships(), fetch_group(), fetch_groups(), fetch_members() (+16 more)

### Community 59 - "Security"
Cohesion: 0.09
Nodes (27): authenticate_mobile_request(), _build_string_to_sign(), _build_string_to_sign_candidates(), _enforce_rate_limit_and_nonce(), _extract_bearer_or_header(), _json_error(), _parse_timestamp(), _verify_device_signature() (+19 more)

### Community 60 - "Students Api"
Cohesion: 0.10
Nodes (34): asId(), createStudent(), deactivateStudents(), emptyPermissions, getStudent(), getStudents(), listPath(), options() (+26 more)

### Community 61 - "Share One Fixed Window"
Cohesion: 0.06
Nodes (15): record_fixed_window(), _Connection, _Cursor, _lockout_run(), test_a_wrong_password_inside_the_window_is_counted(), test_an_old_window_or_an_expired_lock_starts_the_count_again(), test_attendance_rejects_another_class_a_bad_date_and_keeps_one_upsert(), test_bad_lockout_settings_fall_back_to_the_defaults() (+7 more)

### Community 62 - "Face"
Cohesion: 0.10
Nodes (21): readable_template(), decode_template(), encode_template(), _fernet(), is_encrypted(), key_problem(), _multi(), needs_rewrite() (+13 more)

### Community 63 - "Body"
Cohesion: 0.14
Nodes (34): body(), absence_row(), _absences(), _accessible_ids(), _add_absence(), _approve_absence(), _approve_proxy(), _create() (+26 more)

### Community 64 - "Consent Payload"
Cohesion: 0.09
Nodes (24): _consent_payload(), active_consent(), check_recognition(), check_session_code(), _code(), consent_required(), consent_status(), ConsentRequired (+16 more)

### Community 65 - "Binascii"
Cohesion: 0.09
Nodes (20): fetch_faculty_id_by_email(), fetch_invitation(), fetch_student_id_by_email(), fetch_user_id_by_username(), insert_faculty(), insert_student(), insert_user(), mark_invitation_expired() (+12 more)

### Community 66 - "Factories"
Cohesion: 0.08
Nodes (23): LectureDay, csrf_token(), _hod_with(), lecture_day(), _mark(), _marked(), _report(), test_a_denied_report_download_is_the_standard_denial_and_is_audited() (+15 more)

### Community 67 - "Pdf Response"
Cohesion: 0.08
Nodes (16): _pdf_response(), Config, _feature(), _first_existing_path(), _path_from_env(), DevelopmentConfig, get_config(), ProductionConfig (+8 more)

### Community 68 - "Data Access Student Portal"
Cohesion: 0.11
Nodes (21): count_weekly_classes(), fetch_student_id(), fetch_student_profile(), fetch_student_section(), fetch_student_timetable(), fetch_today_classes(), _slot_params(), figures_dict() (+13 more)

### Community 69 - "Rules"
Cohesion: 0.09
Nodes (20): _clean_param(), clean_rules(), default_rules(), effective_rules(), _hhmm(), legacy_rules(), load_document(), load_preferences() (+12 more)

### Community 70 - "Cohort Key"
Cohesion: 0.11
Nodes (28): cohort_key(), solve_targets(), _booking(), _error(), _ok(), _slot(), test_a_hod_request_waits_for_approval_then_blocks_manual_slots_and_the_generator(), test_a_request_against_a_timetabled_slot_is_refused_with_free_rooms_of_that_type() (+20 more)

### Community 71 - "Student Sync"
Cohesion: 0.09
Nodes (22): _judge_event(), open_lecture_session(), _record_synced_lesson(), reprocess_failed_logs(), _roster_payload(), upload_attendance_logs(), _user_id_of_student(), emit_marked_webhooks() (+14 more)

### Community 72 - "Testing"
Cohesion: 0.06
Nodes (15): loaded_for_cli_command(), _Connection, _Cursor, _SeedCursor, test_branding_seed_adds_missing_defaults_and_never_overwrites(), test_cli_detection_counts_run_as_serving(), test_create_app_outside_the_cli_is_not_a_cli_command(), test_database_reason_reads_the_stamp_and_closes_the_connection() (+7 more)

### Community 73 - "Response Envelope"
Cohesion: 0.11
Nodes (35): log_activity, JSON API, Audit log service, Remaining Flask views, data_access, DESIGN_INSTITUTIONS.md, Modules, Frontend academics (+27 more)

### Community 74 - "Export Jobs"
Cohesion: 0.11
Nodes (25): _audit_query(), _claim_next(), _complete(), _export_audit(), _export_report(), _export_timetable(), _export_users(), _fail() (+17 more)

### Community 75 - "Data Access Invitations"
Cohesion: 0.09
Nodes (17): count_invitations(), expire_invitation(), fetch_invitation_stats(), fetch_invitation_status(), fetch_invitation_token(), fetch_invitations(), fetch_named_rows(), fetch_pending_invitation() (+9 more)

### Community 76 - "Fetch Permissions With Description"
Cohesion: 0.10
Nodes (17): fetch_permissions_with_description(), delete_user_group(), fetch_active_user_group(), fetch_classes(), fetch_courses(), fetch_department_name(), fetch_departments(), fetch_group_name() (+9 more)

### Community 77 - "Active"
Cohesion: 0.10
Nodes (21): active(), applies_on(), _approved_rows(), _as_date(), as_time(), booked_room(), create(), hhmm() (+13 more)

### Community 78 - "Persist Cohort"
Cohesion: 0.09
Nodes (25): persist_cohort(), add_slot(), on_timetable_published(), _deliveries(), endpoint(), _get(), _key(), _remember_app() (+17 more)

### Community 79 - "Minutes"
Cohesion: 0.09
Nodes (18): _minutes(), times_overlap(), candidate_rooms_clause(), fetch_candidate_rooms(), booking_conflicts(), BookingError, cancel(), decide() (+10 more)

### Community 80 - "Admin"
Cohesion: 0.09
Nodes (16): admin(), attendance(), face(), notifications_group(), db_adopt(), _read_live(), register_commands(), seed() (+8 more)

### Community 81 - "Data Access Profile"
Cohesion: 0.10
Nodes (17): fetch_department_name(), fetch_faculty_email(), fetch_password_hash(), fetch_profile_form(), fetch_profile_user(), fetch_student_email(), update_faculty_email(), update_password() (+9 more)

### Community 82 - "Production Requirements"
Cohesion: 0.06
Nodes (36): Production requirements, gunicorn 23.0.0, blinker 1.9.0, cffi 2.0.0, charset-normalizer 3.4.7, click 8.3.1, colorama 0.4.6, cryptography 46.0.3 (+28 more)

### Community 83 - "Timetable"
Cohesion: 0.09
Nodes (21): active(), assess(), _clean_bounds(), clean_norms(), designations(), enforcement(), _faculty_rows(), limits_for() (+13 more)

### Community 84 - "Counts Attended"
Cohesion: 0.10
Nodes (18): counts_as_attended(), counts_in_denominator(), percentage(), _Tally, Figures, component_of(), daily_trend(), Inputs (+10 more)

### Community 85 - "Bulk Set Day Availability"
Cohesion: 0.07
Nodes (16): bulk_set_day_availability(), _Connection, _Cursor, _DictionaryConnection, test_availability_view_is_a_weekly_grid_without_raw_slots(), test_bulk_availability_reports_error_and_rolls_back(), test_bulk_availability_reports_ok_without_leaving_the_connection_open(), test_day_change_keeps_the_shift_until_the_checkbox_clears_it() (+8 more)

### Community 86 - "Get Connection"
Cohesion: 0.12
Nodes (23): get_db_connection(), allocated_targets(), _claim_next(), _close_draft(), _cohort_label(), enqueue_job(), ensure_worker(), _finish() (+15 more)

### Community 87 - "Role Permissions"
Cohesion: 0.17
Nodes (28): api(), form_post(), _actor(), _direct_grants(), _edit(), _held_and_unheld(), _hod_with_roles(), _role() (+20 more)

### Community 88 - "Catalog Assessment"
Cohesion: 0.17
Nodes (32): _change_denied(), _component(), _fail(), _load_component(), _lock(), _lock_denied(), _mark_write(), _marks() (+24 more)

### Community 89 - "Create App"
Cohesion: 0.11
Nodes (24): create_app, How the application works, Flask API, Mobile sync API, MySQL, page-access.ts, React router, Sign-in roles (+16 more)

### Community 90 - "Seeders Base"
Cohesion: 0.12
Nodes (11): ids_by_name(), record(), recorded(), SeedResult, BrandingSeeder, default_seeders(), run_seeders(), PermissionsSeeder (+3 more)

### Community 91 - "Data Permissions"
Cohesion: 0.15
Nodes (17): default_pairs(), execute(), ledger(), mapping(), seed(), snapshot(), unique_keys(), test_seed_run_on_a_fresh_database_grants_every_default() (+9 more)

### Community 92 - "Timetable Services"
Cohesion: 0.15
Nodes (28): Timetable services, Timetable API, Timetable rules API, Room bookings, DESIGN_CAPABILITIES.md, Generating timetables, Faculty window preferences, Timetable generate API (+20 more)

### Community 93 - "Util"
Cohesion: 0.07
Nodes (9): test_upgrade_refuses_while_any_mark_has_no_session(), _Connection, _load(), _Result, revision(), test_0009_follows_0008(), test_downgrade_drops_only_existing_columns(), test_nothing_runs_when_already_applied() (+1 more)

### Community 94 - "Holidays For Week"
Cohesion: 0.08
Nodes (16): holidays_for_week(), load_lab_batches(), _allowed_rooms(), _coerce_time(), _entries_for(), _explain(), _gap_vars(), _hhmm_to_time() (+8 more)

### Community 95 - "User Access"
Cohesion: 0.18
Nodes (26): _access(), _bulk(), _denied(), _grant(), _grant_group(), _grant_many(), _grant_result(), _manage_denied() (+18 more)

### Community 96 - "Reports Admin Common"
Cohesion: 0.12
Nodes (20): _clean_filters(), _create_csv_response(), _get_redirect_target(), _write_csv_file(), _build_report_export_dataset(), _build(), _cohort_filters(), _queue() (+12 more)

### Community 97 - "Get User Accessible Departments"
Cohesion: 0.11
Nodes (15): get_user_accessible_departments(), get_accessible_departments(), can_manage_module(), can_view_module(), get_accessible_departments(), get_user_department(), get_user_perms(), get_user_perms_by_module() (+7 more)

### Community 98 - "Calendar"
Cohesion: 0.12
Nodes (16): cohort_reports(), defaulters(), policy(), _cohort(), _dates(), defaulter_rows(), _int(), _meta() (+8 more)

### Community 99 - "Faculty Attendance Page"
Cohesion: 0.10
Nodes (28): Activity, FacultyAttendancePage(), load(), show(), turn(), percentText(), statusClass(), Summary (+20 more)

### Community 100 - "Clashes"
Cohesion: 0.10
Nodes (11): cohort_timetable_clashes(), faculty_timetable_free(), fetch_absence_lectures(), fetch_proxy_candidates(), insert_proxy_log(), assign_admin_proxy(), faculty_is_free(), _notify_proxy() (+3 more)

### Community 101 - "Settings"
Cohesion: 0.14
Nodes (17): _change_denied(), _consume_flash(), _fields_valid(), _list(), _public_settings(), register_settings_routes(), _reset(), _save() (+9 more)

### Community 102 - "Sharing Input"
Cohesion: 0.14
Nodes (23): sharing_input(), _can(), _capacity(), _department_id(), _input_error(), _institution_choices(), _owned(), _permission_error() (+15 more)

### Community 103 - "Admin Timetable"
Cohesion: 0.07
Nodes (13): assign_timetable_room(), deactivate_timetable_session(), delete_timetable_session(), fetch_classes(), fetch_courses(), fetch_divisions(), fetch_room_conflicts(), fetch_room_type() (+5 more)

### Community 104 - "Audit Cli"
Cohesion: 0.14
Nodes (17): _audit_cli(), backfill_sessions(), BackfillReport, _groups(), at_0007(), history(), _mark(), _revision() (+9 more)

### Community 105 - "Clean Preferences"
Cohesion: 0.13
Nodes (17): clean_preferences(), evaluate(), _overlaps(), _Bind, _load_0016(), _only(), _Result, _row() (+9 more)

### Community 106 - "Versions"
Cohesion: 0.11
Nodes (20): active(), _cell_key(), _change(), _cohort(), cohorts_of(), create_draft(), _diff_cohort(), _hhmm() (+12 more)

### Community 107 - "Change User"
Cohesion: 0.11
Nodes (12): change_user(), _App, _bind(), _Connection, _Cursor, _Logger, test_activating_a_locked_account_unlocks_it(), test_bad_department_id_rolls_back() (+4 more)

### Community 108 - "Timetable Features"
Cohesion: 0.13
Nodes (15): _clamp01(), extract_timetable_features(), _clamp01(), _default_model_path(), _feature_vector(), _load_model(), predict_quality_score(), _sigmoid() (+7 more)

### Community 109 - "Build Scope"
Cohesion: 0.15
Nodes (17): build_scope(), count_active_institutions(), _Cursor, _institution(), _load_0014(), _membership(), test_0014_backfill_runs_only_on_empty_tables_and_in_the_right_phase(), test_0014_creates_only_what_is_missing_and_drops_only_what_exists() (+9 more)

### Community 110 - "Fetch Allocated Faculty"
Cohesion: 0.10
Nodes (13): fetch_allocated_faculty(), fetch_class_overlap(), fetch_course_program(), fetch_faculty_overlap(), insert_timetable_session(), candidate_faculty_clause(), count_slot_sessions(), _check_sharing() (+5 more)

### Community 111 - "Availability Absence Copies"
Cohesion: 0.14
Nodes (20): Availability and absence copies, academic_rules/availability.py, Clash check copies, academic_rules/clashes.py, Date and time parsing copies, Duplication report, core/exceptions.py, services/face embeddings (+12 more)

### Community 112 - "Courses Api"
Cohesion: 0.17
Nodes (25): asCourse(), asId(), CourseDraft, CourseList, CoursePermissions, CourseRecord, createCourse(), deleteCourse() (+17 more)

### Community 113 - "Assign Rooms"
Cohesion: 0.20
Nodes (21): _assign_rooms(), Demand, _pool(), Problem, solve(), _cells(), _demand(), test_a_demand_restricted_to_its_cohort_days_stays_on_them() (+13 more)

### Community 114 - "Account GET Api Session"
Cohesion: 0.18
Nodes (21): signed_in_as(), _by_name(), _error(), _ok(), test_admin_reads_but_cannot_change_and_teachers_see_nothing(), test_invalid_input_is_refused(), test_server_flag_off_hides_the_feature_despite_the_tenant_switch(), test_session_reports_defaults_and_toggles_follow_saves() (+13 more)

### Community 115 - "Cohort Slots Clash"
Cohesion: 0.14
Nodes (13): cohort_slots_clash(), _chose(), _in_batch(), in_roster(), Slot, Student, _slot(), test_fetch_lecture_roster_agrees_with_in_roster() (+5 more)

### Community 116 - "Reports"
Cohesion: 0.14
Nodes (21): _audit_export_denied(), _audit_export_filters(), _available_types(), _cached_options(), _copy_dates(), _copy_id(), _download(), _download_denied() (+13 more)

### Community 117 - "Timetable Versions"
Cohesion: 0.19
Nodes (20): _can_publish(), _cohort_filter(), _diff(), _discard(), _gate(), _list(), _one(), _owned() (+12 more)

### Community 118 - "Departments Api"
Cohesion: 0.18
Nodes (24): asDepartment(), asId(), createDepartment(), deleteDepartment(), DepartmentDraft, DepartmentList, DepartmentPermissions, DepartmentRecord (+16 more)

### Community 119 - "Sign Student Teacher Redirect"
Cohesion: 0.14
Nodes (13): sign_in(), _App, _bind(), _Connection, _Cursor, _Logger, test_several_student_rows_do_not_pick_one(), test_student_sign_in_keeps_session_and_query_order() (+5 more)

### Community 120 - "Booking When"
Cohesion: 0.14
Nodes (17): _booking_when(), _cohort_label(), _email_of_user(), enqueue(), _hods(), _institution(), not_marked_digest(), on_booking_decision() (+9 more)

### Community 121 - "Create User"
Cohesion: 0.13
Nodes (11): create_user(), _App, _bind(), _Connection, _Cursor, _Logger, test_a_role_the_actor_may_not_manage_is_refused(), test_blank_password_is_stored_empty() (+3 more)

### Community 122 - "Institution Input"
Cohesion: 0.20
Nodes (19): institution_input(), _as_date(), _cancel(), _create(), _decide(), _free_rooms(), _gate(), _hhmm() (+11 more)

### Community 123 - "Exceptions"
Cohesion: 0.12
Nodes (9): AppError, ForbiddenError, NotFoundError, UnavailableError, client(), blocked_probe(), custom_probe(), not_found_probe() (+1 more)

### Community 124 - "Shifts"
Cohesion: 0.17
Nodes (19): availability(), create_pattern(), _day(), pattern_row(), patterns(), register_shift_routes(), remove_pattern(), request_view() (+11 more)

### Community 125 - "Insert Processed Absence"
Cohesion: 0.11
Nodes (9): insert_processed_absence(), add_faculty_absence(), _admin_find_and_assign_proxy(), _bind(), _Connection, _Cursor, test_admin_absence_is_stored_as_processed(), test_duplicate_faculty_username_closes_both_without_commit() (+1 more)

### Community 126 - "Error"
Cohesion: 0.13
Nodes (12): classify(), execute_batch(), execute_create_tables_with_retry(), execute_inserts_with_retry(), get_db_config(), is_fk_dependency_error(), is_fk_insert_error(), load_dotenv_file() (+4 more)

### Community 127 - "Test Admin Login"
Cohesion: 0.13
Nodes (10): _App, _bind(), _Connection, _Cursor, _Logger, test_admin_sign_in_stores_the_username_as_the_display_name(), test_password_check_error_stays_on_the_login_response(), test_unknown_and_blocked_admin_accounts_do_not_commit() (+2 more)

### Community 128 - "Catalog Exams"
Cohesion: 0.24
Nodes (21): _change_denied(), _create(), _delete(), _exam(), _fail(), _off(), _open(), _page() (+13 more)

### Community 129 - "Process Wide Registry For"
Cohesion: 0.16
Nodes (3): Registry, _row_to_tenant(), test_resolve_caches_hostname_lookups_until_they_expire()

### Community 130 - "Generator"
Cohesion: 0.15
Nodes (15): build_time_slots(), _course_institution(), generate_timetable_for_class(), build_distributed_sessions(), clone_faculty_busy_state(), clone_room_usage_state(), faculty_is_available(), find_available_room() (+7 more)

### Community 131 - "Test Remaining Extracts"
Cohesion: 0.13
Nodes (10): _bind(), _Connection, _Cursor, test_bulk_action_naming_a_protected_account_or_yourself_is_refused(), test_bulk_activate_updates_teachers_and_students(), test_pagination_counts_before_the_page_and_rejects_a_query_without_from(), test_proxy_assignment_ignores_the_active_flag_and_leaves_the_connection_open(), test_short_bulk_password_does_not_roll_back() (+2 more)

### Community 132 - "Data Access Attendance Calc"
Cohesion: 0.15
Nodes (13): fetch_batch_memberships(), fetch_excuses(), fetch_marks(), fetch_selections(), fetch_sessions(), fetch_slots(), fetch_student(), fetch_student_by_user() (+5 more)

### Community 133 - "Count Active Sessions"
Cohesion: 0.09
Nodes (11): count_active_sessions(), count_filtered(), fetch_actions(), fetch_critical_actions(), fetch_daily_activity(), fetch_entity_types(), fetch_failed_logins(), fetch_recent_sessions() (+3 more)

### Community 134 - "Sessions"
Cohesion: 0.10
Nodes (3): require_valid_session(), decorated_function(), SessionManager

### Community 135 - "Services Notifications"
Cohesion: 0.16
Nodes (13): _claim(), _config(), load_settings(), _max_attempts(), process_one(), _retry_seconds(), _room_approvers(), _roster_users() (+5 more)

### Community 136 - "Test Registration"
Cohesion: 0.18
Nodes (13): _App, _bind(), _capture_form(), _Connection, _Cursor, _invitation(), test_invalid_used_and_expired_links(), test_missing_capture_does_not_roll_back() (+5 more)

### Community 137 - "App Errorhandler"
Cohesion: 0.18
Nodes (12): app_error(), _app_error_response(), _debug_on(), _detail_text(), error_document(), error_response(), forbidden_error(), handle_exception() (+4 more)

### Community 138 - "Check Maintenance Mode"
Cohesion: 0.17
Nodes (14): check_maintenance_mode(), test_admin_staff_can_use_the_admin_panel_only(), test_api_maintenance_response_has_no_application_detail(), test_maintenance_is_off_is_not_this_modules_job(), test_page_maintenance_response_is_a_page(), test_page_uses_the_configured_notice(), test_students_and_teachers_stay_on_the_maintenance_page(), test_visitors_can_open_admin_sign_in_and_the_public_reads() (+6 more)

### Community 139 - "Test Notifications"
Cohesion: 0.17
Nodes (12): _app(), _Bind, _Connection, _load_0011(), _Result, _row(), test_0011_follows_0010_and_creates_only_missing_tables(), test_process_one_defers_without_burning_an_attempt_when_nothing_can_send() (+4 more)

### Community 140 - "Proxy"
Cohesion: 0.18
Nodes (16): _approve(), _choice_row(), _choices(), _clock12(), _count(), _decision_error(), _list(), _note() (+8 more)

### Community 141 - "Test Active Config"
Cohesion: 0.19
Nodes (12): _imports_global_config(), test_no_application_module_imports_the_global_config(), _assigned_strings(), _called(), checked_names(), _files(), _parse(), _string_tables() (+4 more)

### Community 142 - "Academic Term"
Cohesion: 0.16
Nodes (11): Academic term, Academic calendar, syllabus, assessments and exams, teaching_weeks, 0019_academic_calendar, 0020_syllabus, 0021_assessment, 0022_exam_schedule, Public API /api/v1 (+3 more)

### Community 143 - "Tsconfig App"
Cohesion: 0.10
Nodes (19): compilerOptions, allowImportingTsExtensions, jsx, lib, module, moduleDetection, moduleResolution, noEmit (+11 more)

### Community 144 - "0009 Worker Claims"
Cohesion: 0.18
Nodes (13): downgrade(), _has_column(), upgrade(), backfill_statements(), _count(), downgrade(), downgrade_statements(), _existing() (+5 more)

### Community 145 - "Queue Test Message"
Cohesion: 0.25
Nodes (14): queue_test_message(), run_tenant(), cursor(), _rows(), test_a_recipient_without_an_address_is_recorded_as_skipped(), test_an_elective_cancellation_reaches_only_the_students_who_chose_it(), test_cancelling_a_lecture_queues_one_notice_per_roster_student_and_the_teacher(), test_close_day_triggers_queue_the_digest_and_defaulter_alerts_once() (+6 more)

### Community 146 - "Build"
Cohesion: 0.16
Nodes (14): build(), _error(), _key(), _ok(), test_assessment_off_hides_marks_and_on_locks_them_before_students_see_them(), _error(), _event(), _key() (+6 more)

### Community 147 - "Hhmm"
Cohesion: 0.14
Nodes (9): _hhmm(), slot_cost(), _arrange(), _Cursor, test_check_slot_lists_every_broken_rule_and_add_slot_raises_the_first(), test_exclude_id_reaches_the_overlap_queries_and_the_room_check(), test_hhmm_accepts_the_shapes_mysql_returns(), test_slot_cost_is_none_when_preferences_are_off() (+1 more)

### Community 148 - "Deactivate User"
Cohesion: 0.15
Nodes (7): deactivate_user(), _bind(), _Connection, _Cursor, test_failed_deactivation_rolls_back(), test_missing_and_protected_accounts_are_not_deactivated(), test_teacher_deactivation_marks_the_faculty_row()

### Community 149 - "Test Uploads Transaction"
Cohesion: 0.14
Nodes (9): _Connection, test_save_uploaded_file_keeps_the_branding_name(), test_save_uploaded_file_rejects_a_disallowed_extension(), test_transaction_commits_when_the_block_finishes(), test_transaction_ignores_a_missing_connection(), test_transaction_rolls_back_without_committing_when_the_block_raises(), _upload(), save_uploaded_file() (+1 more)

### Community 150 - "Delete Faculty Availability"
Cohesion: 0.12
Nodes (10): delete_faculty_availability(), fetch_active_shift_patterns(), fetch_availability_slots(), fetch_availability_with_shifts(), fetch_faculty_name_user(), insert_availability_slot(), insert_unavailable_day(), _save_form_availability() (+2 more)

### Community 151 - "Account Authority"
Cohesion: 0.12
Nodes (10): flask admin create-superadmin, Permission canon, Unenforced permissions, Institution memberships, Institution follow-ups, Face templates, Reports and exports, Report export queue (+2 more)

### Community 152 - "Open Lab Batch Audit"
Cohesion: 0.13
Nodes (19): Open lab-batch audit xfail, 0009_worker_claims, 0010_face_safeguards, 0011_notifications, 0012_lab_batches, 0013_integrations, 0014_institutions, Institutions (+11 more)

### Community 153 - "Tenant Connection Settings"
Cohesion: 0.25
Nodes (14): Tenant connection settings, Tenancy, Tenant health check, Tenancy live tests, Tenant mobile devices, Tenant registry schema, Tenant request routing, Single college mode (+6 more)

### Community 154 - "Tsconfig Node"
Cohesion: 0.11
Nodes (18): compilerOptions, allowImportingTsExtensions, lib, module, moduleDetection, moduleResolution, noEmit, noFallthroughCasesInSwitch (+10 more)

### Community 155 - "College Timetable"
Cohesion: 0.20
Nodes (14): college_timetable.sql, 2026-03-30 data dump, Legacy scripts, hash_passwords.py, run_full_migration, Alembic revisions, migrations/_archive, docs/DATABASE.md (+6 more)

### Community 156 - "Authority"
Cohesion: 0.20
Nodes (12): group_permission_names(), held_permission_names(), is_super_admin(), may_manage_role(), permission_names_for_ids(), role_level(), role_level_by_id(), role_permission_ids() (+4 more)

### Community 157 - "Black Background"
Cohesion: 0.14
Nodes (19): Black background, Black contour, Blue hoodie, Closed crescent eyes, Black, Blue, Cyan, White (+11 more)

### Community 158 - "Cohort Names"
Cohesion: 0.17
Nodes (14): cohort_names(), name(), _ids(), _sweep(), test_get_routes_do_not_return_500(), blueprint_name(), declared_methods(), get_targets() (+6 more)

### Community 159 - "Test Face Safeguards"
Cohesion: 0.23
Nodes (16): audit_rows(), consent(), event(), lecture_day(), signed(), stored_template(), sync(), test_devices_mark_only_the_lecture_the_teacher_opened() (+8 more)

### Community 160 - "Test Admin Portal Extract"
Cohesion: 0.13
Nodes (5): _bind(), _Connection, _Cursor, test_availability_commits_the_delete_before_inserts(), test_teacher_absence_inserts_unprocessed()

### Community 161 - "Test Profile"
Cohesion: 0.14
Nodes (7): _bind(), _Connection, _Cursor, test_password_change_stores_the_new_hash(), test_profile_save_without_a_photo_updates_the_faculty_email(), test_teacher_profile_uses_the_faculty_email_when_the_account_email_is_empty(), test_wrong_password_does_not_roll_back()

### Community 162 - "When Tenant Has One"
Cohesion: 0.22
Nodes (5): Scope, test_chosen_institution_restricts_every_predicate_to_it(), test_member_of_several_institutions_without_a_choice_sees_all_of_them(), test_single_institution_tenant_sees_everything_with_no_predicates(), test_super_admin_sees_the_organization_until_they_pick_an_institution()

### Community 163 - "Fetch Departments"
Cohesion: 0.11
Nodes (8): fetch_departments(), fetch_faculty_totals(), can_access_department(), get_accessible_faculty_ids(), get_accessible_student_ids(), get_department_filter_clause(), query_page(), list_faculty()

### Community 164 - "Record Logout Deactivate That"
Cohesion: 0.19
Nodes (8): sign_out(), _bind(), _Connection, _Cursor, test_anonymous_logout_only_clears_the_session(), test_failed_deactivation_leaves_the_session_in_place(), test_logout_deactivates_the_session_and_logs_it_in_one_commit(), test_logout_without_a_session_id_still_logs_the_user()

### Community 165 - "Deactivate Session"
Cohesion: 0.18
Nodes (9): deactivate_session(), fetch_log(), run_query(), _append_filters(), _column_clause(), _cursor(), export_audit_rows(), load_log_detail() (+1 more)

### Community 166 - "Renderers"
Cohesion: 0.24
Nodes (12): _cell(), _escape(), institution_name(), label_for(), _meta_lines(), normalise_format(), render(), write_csv() (+4 more)

### Community 167 - "Find User"
Cohesion: 0.16
Nodes (6): find_user(), _Connection, _Cursor, test_failed_lookup_still_closes(), test_found_user_loads_roles_and_keeps_the_response_shape(), test_missing_user_does_not_load_roles()

### Community 168 - "Query"
Cohesion: 0.33
Nodes (13): test_users_manage_permissions_is_in_the_canon_and_granted_to_no_role_but_super_admin(), test_queued_pdf_report_downloads_as_pdf(), _cohort(), _error(), _live(), _ok(), _run_job(), _teachable() (+5 more)

### Community 169 - "0001 Baseline Existing Schema"
Cohesion: 0.14
Nodes (3): downgrade(), _run(), upgrade()

### Community 170 - "Request"
Cohesion: 0.17
Nodes (10): bind_session(), install(), resolve_tenant(), stamp_tenant_session(), _refuse(), resolve_request(), stamp_session(), _wants_json() (+2 more)

### Community 171 - "Data Access Audit Logs"
Cohesion: 0.18
Nodes (8): count_failed_matches(), count_session_matches(), fetch_failed_page(), fetch_session_page(), _panel_clause(), load_failed_page(), load_session_page(), _page_window()

### Community 172 - "Services"
Cohesion: 0.16
Nodes (5): list_users(), _Connection, _Cursor, test_failed_user_query_leaves_the_cursor_open(), test_user_filters_keep_role_status_and_username_order()

### Community 173 - "Busy Clause"
Cohesion: 0.19
Nodes (11): busy_clause(), _cohort_key(), diff(), _load_0017(), _slot(), test_0017_follows_0016_and_creates_only_what_is_missing(), test_busy_clause_counts_other_draft_rows_and_ignores_live_rows_of_covered_cohorts(), test_diff_classifies_unchanged_moved_added_removed_and_room_changes() (+3 more)

### Community 174 - "Delete Rows"
Cohesion: 0.13
Nodes (8): _delete_rows(), discard(), prune_drafts(), rename(), _Cursor, test_prune_drafts_keeps_the_newest_and_the_protected_one(), test_prune_drafts_without_protection_keeps_exactly_keep(), test_rename_rejects_blank_or_long_labels()

### Community 175 - "Test Permission Matrix"
Cohesion: 0.18
Nodes (11): _attendance_updated(), Case, _grant_user_permission(), _hod(), _put_role_permissions(), _reset_password(), test_no_session_is_401(), test_with_the_permission_succeeds() (+3 more)

### Community 176 - "Test Split Connection Locks"
Cohesion: 0.26
Nodes (12): _audited(), _change_own_password(), _edit_own_account(), _hod_who_edits_roles(), _logged(), _rename_own_role(), test_an_audit_failure_rolls_the_change_back(), test_changing_your_own_password_is_audited() (+4 more)

### Community 177 - "Test Admin Screen Extract"
Cohesion: 0.15
Nodes (4): _Connection, _Cursor, test_audit_list_counts_before_paging_and_leaves_the_connection_open(), test_shift_delete_uses_the_private_connection_and_a_plain_cursor()

### Community 178 - "Cryptography Fernet"
Cohesion: 0.23
Nodes (7): _config_value(), decrypt_text(), encrypt_text(), _fernet(), key_source(), test_an_invalid_key_is_reported_not_swallowed_on_encrypt(), test_secrets_use_the_settings_key_then_the_face_key_then_secret_key()

### Community 179 - "Schema Ownership"
Cohesion: 0.19
Nodes (8): 0001_baseline, flask db-adopt, Database and migrations, MariaDB 10.4.32, 0008_attendance_views, Startup schema check, Attendance calculation foundation, Attendance calculation phases

### Community 180 - "Notification Settings Page"
Cohesion: 0.19
Nodes (14): emptySettings, NotificationSettingsPage(), apply(), loadOutbox(), save(), sendTest(), OutboxRow, Payload (+6 more)

### Community 181 - "Concurrency"
Cohesion: 0.14
Nodes (13): concurrency, cancel-in-progress, env, PIP_DISABLE_PIP_VERSION_CHECK, PYTHONDONTWRITEBYTECODE, jobs, unit, name (+5 more)

### Community 183 - "Notifications Off"
Cohesion: 0.15
Nodes (4): NotificationsOff, send(), test_send_builds_the_message_and_talks_smtp(), test_send_without_an_account_raises_notifications_off()

### Community 184 - "Format Time Filter"
Cohesion: 0.23
Nodes (4): format_time_filter(), test_format_hhmm_matches_previous_rules(), test_the_template_filter_delegates(), format_hhmm()

### Community 185 - "Teaching Day Scheduling Cancellation"
Cohesion: 0.24
Nodes (4): flask attendance close-day, 0007_lecture_sessions, Nightly close-day job, lecture_sessions

### Community 186 - "Default Avatar"
Cohesion: 0.23
Nodes (10): Default user avatar, Background circle, Bootstrap secondary gray, Gray circular background, White circular head, Head circle, Shoulder path, White shoulder shape (+2 more)

### Community 188 - "Util"
Cohesion: 0.29
Nodes (6): get_engine(), get_engine_url(), process_revision_directives(), refuse_autogenerate(), run_migrations_offline(), run_migrations_online()

### Community 189 - "Audit"
Cohesion: 0.22
Nodes (3): _audit(), Report, to_mark()

### Community 190 - "Fetch Activity Summary"
Cohesion: 0.18
Nodes (6): fetch_activity_summary(), fetch_audit_user(), fetch_recent_activities(), fetch_user_sessions(), load_user_activity(), test_missing_audit_user_leaves_the_connection_open()

### Community 191 - "Shared Job Claim Columns"
Cohesion: 0.22
Nodes (3): 0015_capabilities, Capabilities, Health and incidents

### Community 192 - "MYSQL CLIENT"
Cohesion: 0.20
Nodes (11): MYSQL_CLIENT, MYSQLDUMP, steps, env, name, with, steps, cache (+3 more)

### Community 193 - "0008 Attendance Views"
Cohesion: 0.27
Nodes (7): downgrade(), downgrade_statements(), refusal(), _state(), upgrade(), upgrade_statements(), view_statements()

### Community 194 - "Isolation"
Cohesion: 0.27
Nodes (3): Baseline, _checksums(), _tables()

### Community 195 - "0016 Timetable Preferences"
Cohesion: 0.31
Nodes (5): 0016_timetable_preferences, 0017_timetable_versions, 0018_bookings, CAPABILITIES registry, TIMETABLE.md

### Community 196 - "0019 Academic Calendar"
Cohesion: 0.51
Nodes (8): _columns(), _constraints(), downgrade(), _has_table(), _indexes(), _names(), _reason_type(), upgrade()

### Community 197 - "Test Timetable Grid"
Cohesion: 0.42
Nodes (8): _error(), _ok(), _slot(), test_check_lists_every_clash_and_exclude_id_lets_a_slot_move_onto_itself(), test_check_mirrors_add_slot_on_the_same_payload(), test_check_reports_the_soft_rule_cost_of_a_clean_move(), test_students_and_teachers_without_the_permission_cannot_check_or_browse_by_teacher(), test_teacher_and_room_views_span_cohorts_and_carry_the_ids_the_grid_moves()

### Community 198 - "Test Error Pages"
Cohesion: 0.31
Nodes (6): _client(), test_debug_off_hides_the_exception_on_the_page(), test_debug_off_keeps_the_api_message_generic(), test_debug_on_puts_the_message_in_the_api_error(), test_debug_on_shows_the_message_without_a_traceback(), test_missing_page_is_a_404_without_a_framework_message()

### Community 199 - "Face Embedding"
Cohesion: 0.22
Nodes (3): FaceEmbeddingResult, get_face_pipeline(), _load_interpreter_class()

### Community 200 - "MARIADB PASSWORD"
Cohesion: 0.22
Nodes (9): MARIADB_PASSWORD, MARIADB_ROOT_PASSWORD, MARIADB_USER, services, env, image, options, ports (+1 more)

### Community 201 - "Script"
Cohesion: 0.22
Nodes (8): API, App, CascadingDropdowns, DataTable, FileUpload, FormHandlers, TimetablePreview, Utils

### Community 202 - "Test Academic Calendar"
Cohesion: 0.47
Nodes (7): _error(), _ok(), _placed_days(), _terms(), test_capability_off_ignores_terms_and_the_api_is_hidden(), test_teaching_term_gates_generation_close_day_and_cancels_exam_sessions(), _year()

### Community 203 - "Attendance Calculation Service"
Cohesion: 0.43
Nodes (3): Attendance calculation service, in_roster, Notification triggers

### Community 204 - "Attendance Admin Common"
Cohesion: 0.36
Nodes (3): _decimal_to_number(), _promote_log_to_attendance(), _promote_log_to_faculty_attendance()

### Community 206 - "Runs"
Cohesion: 0.33
Nodes (7): name, runs-on, steps, steps, deploy-files, run, uses

### Community 207 - "0003 Security Schema"
Cohesion: 0.38
Nodes (4): _column_exists(), role_level_statements(), upgrade(), test_security_migration_is_idempotent()

### Community 208 - "0007 Lecture Sessions"
Cohesion: 0.48
Nodes (5): downgrade(), downgrade_statements(), _existing(), upgrade(), upgrade_statements()

### Community 209 - "0012 Lab Batches"
Cohesion: 0.48
Nodes (5): downgrade(), downgrade_statements(), _existing(), upgrade(), upgrade_statements()

### Community 210 - "0017 Timetable Versions"
Cohesion: 0.48
Nodes (5): downgrade(), downgrade_statements(), _existing(), upgrade(), upgrade_statements()

### Community 211 - "0018 Bookings"
Cohesion: 0.48
Nodes (5): downgrade(), downgrade_statements(), _existing(), upgrade(), upgrade_statements()

### Community 212 - "0020 Syllabus"
Cohesion: 0.48
Nodes (5): downgrade(), downgrade_statements(), _existing(), upgrade(), upgrade_statements()

### Community 213 - "0021 Assessment"
Cohesion: 0.48
Nodes (5): downgrade(), downgrade_statements(), _existing(), upgrade(), upgrade_statements()

### Community 214 - "0022 Exam Schedule"
Cohesion: 0.48
Nodes (5): downgrade(), downgrade_statements(), _existing(), upgrade(), upgrade_statements()

### Community 215 - "After Close Day"
Cohesion: 0.29
Nodes (4): after_close_day(), defaulter_alerts(), on_defaulters(), test_after_close_day_runs_both_triggers_and_never_raises()

### Community 218 - "Runs"
Cohesion: 0.33
Nodes (6): name, runs-on, steps, audit, continue-on-error, working-directory

### Community 219 - "Defaults"
Cohesion: 0.33
Nodes (6): run, defaults, name, runs-on, frontend, working-directory

### Community 220 - "0006 Sign Lock"
Cohesion: 0.60
Nodes (5): downgrade(), downgrade_statements(), _existing(), upgrade(), upgrade_statements()

### Community 221 - "Stored Score Document Version"
Cohesion: 0.33
Nodes (4): _json(), scores(), summarize_scores(), test_scores_and_summary_tolerate_missing_or_broken_documents()

### Community 222 - "0010 Face Safeguards"
Cohesion: 0.60
Nodes (3): downgrade(), _has_table(), upgrade()

### Community 223 - "0011 Notifications"
Cohesion: 0.60
Nodes (3): downgrade(), _has_table(), upgrade()

### Community 224 - "0013 Integrations"
Cohesion: 0.60
Nodes (3): downgrade(), _has_table(), upgrade()

### Community 225 - "0016 Timetable Preferences"
Cohesion: 0.60
Nodes (3): downgrade(), _has_table(), upgrade()

### Community 227 - "Needs"
Cohesion: 0.50
Nodes (4): live, name, needs, runs-on

## Ambiguous Edges - Review These
- `Timetable Management documentation` → `MariaDB 10.4.32`  [AMBIGUOUS]
  docs/README.md · relation: conceptually_related_to
- `test_migration_baseline.py` → `Migration-baseline test citation gap`  [AMBIGUOUS]
  docs/DESIGN_ATTENDANCE_CALCULATION.md · relation: conceptually_related_to
- `Open lab-batch audit xfail` → `lab_batch_groups`  [AMBIGUOUS]
  docs/DATABASE.md · relation: conceptually_related_to
- `Attendance calculation phases` → `Lab batches`  [AMBIGUOUS]
  docs/DESIGN_ATTENDANCE_CALCULATION.md · relation: conceptually_related_to
- `Greedy timetable solver` → `routes/timetable_algorithm.py`  [AMBIGUOUS]
  docs/duplication_report.md · relation: conceptually_related_to
- `Joint CP-SAT solver` → `Timetable generation flow`  [AMBIGUOUS]
  docs/system-flows.md · relation: conceptually_related_to
- `Shared solver inputs` → `Faculty id mismatch`  [AMBIGUOUS]
  docs/duplication_report.md · relation: conceptually_related_to
- `React router` → `src/main.tsx`  [AMBIGUOUS]
  frontend/index.html · relation: conceptually_related_to
- `Legacy Flask pages` → `Removed server-rendered blueprints`  [AMBIGUOUS]
  docs/application.md · relation: conceptually_related_to
- `Legacy Flask pages` → `auth blueprint`  [AMBIGUOUS]
  docs/application.md · relation: conceptually_related_to
- `ui/pages.py` → `ui/errors.py`  [AMBIGUOUS]
  docs/application.md · relation: conceptually_related_to
- `Mobile response helpers` → `public_api blueprint`  [AMBIGUOUS]
  docs/duplication_report.md · relation: conceptually_related_to
- `Remaining Flask views` → `app_factory routes`  [AMBIGUOUS]
  docs/modules.md · relation: conceptually_related_to
- `Gray circular background` → `Bootstrap secondary gray`  [AMBIGUOUS]
  static/default-avatar.png · relation: semantically_similar_to
- `Hooded figure` → `Hooded hacker motif`  [AMBIGUOUS]
  static/favicon.png · relation: conceptually_related_to
- `Cyan wireframe spheres` → `Hooded hacker motif`  [AMBIGUOUS]
  static/favicon.png · relation: conceptually_related_to

## Knowledge Gaps
- **56 isolated node(s):** `application.md`, `modules.md`, `system-flows.md`, `route_inventory.md`, `Academic term` (+51 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 2483 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **55 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `login()` connect `Period Statistics` to `Reports Admin Common`, `User`, `Factories`, `Test Timetable Grid`, `Cohort Key`, `Query`, `Test Academic Calendar`, `Persist Cohort`, `Test Permission Matrix`, `Test Split Connection Locks`, `Queue Test Message`, `Build`, `Account GET Api Session`, `Mark Refused`, `Role Permissions`, `Factory`, `Cohort Names`, `Test Face Safeguards`?**
  _High betweenness centrality (0.026) - this node is a cross-community bridge._
- **Are the 82 inferred relationships involving `InputError` (e.g. with `_update()` and `_update_form()`) actually correct?**
  _`InputError` has 82 INFERRED edges - model-reasoned connections that need verification._
- **What connects `application.md`, `modules.md`, `system-flows.md` to the rest of the system?**
  _56 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Attendance Page` be split into smaller, more focused modules?**
  _Cohesion score 0.024776119402985075 - nodes in this community are weakly interconnected._
- **Why does `safe_text()` connect `Slot` to `Catalog Exams`, `Hub`, `Access`, `Permission Denied`, `Registry`, `Handle`, `Proxy`, `Check Maintenance Mode`, `Allowed`, `Courses`, `Integrations`, `Close`, `Handle`, `Account`, `Dashboard`, `Body`, `Consent Payload`, `Export Jobs`, `Get Connection`, `Catalog Assessment`, `User Access`, `Settings`, `Sharing Input`, `Reports`, `Timetable Versions`, `Institution Input`, `Shifts`?**
  _High betweenness centrality (0.022) - this node is a cross-community bridge._

### Low-confidence Hints
_AMBIGUOUS edges — the extractor was unsure. Verify before acting on these._

- **What is the exact relationship between `Timetable Management documentation` and `MariaDB 10.4.32`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `test_migration_baseline.py` and `Migration-baseline test citation gap`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._