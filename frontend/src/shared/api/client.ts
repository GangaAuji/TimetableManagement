const errorMessages: Record<string, string> = {
  unauthorized: 'Sign in to continue.',
  maintenance: 'The system is temporarily unavailable.',
  rate_limited: 'Too many requests. Wait a moment and try again.',
  forbidden: 'You do not have permission to do that.',
  invalid_body: 'The request could not be accepted.',
  blocked: 'The request was blocked.',
  room_number_invalid: 'Enter a room number using letters, numbers, spaces, or - / .',
  room_type_invalid: 'Choose a valid room type.',
  capacity_invalid: 'Capacity must be a positive number.',
  department_invalid: 'Choose a valid department, or leave the room shared.',
  room_number_taken: 'Room number already exists.',
  room_not_found: 'That room was not found.',
  room_in_use: 'This room is used on the timetable, so it cannot be deleted.',
  rooms_unavailable: 'The room list could not be loaded.',
  department_name_invalid: 'Enter a department name up to 100 characters.',
  department_code_invalid: 'Enter a department code using letters, numbers, spaces, or . & / _ -.',
  department_head_invalid: 'Head of department must be 100 characters or fewer.',
  description_invalid: 'Description must be 4000 characters or fewer.',
  department_name_taken: 'A department with this name already exists.',
  department_code_taken: 'A department with this code already exists.',
  department_not_found: 'That department was not found.',
  department_in_use: 'This department has courses or faculty, so it cannot be deleted.',
  departments_unavailable: 'The department list could not be loaded.',
  course_name_invalid: 'Enter a course name up to 100 characters.',
  course_code_invalid: 'Enter a course code using letters, numbers, spaces, or . & / _ -.',
  course_program_invalid: 'Choose UG or PG.',
  course_department_invalid: 'Choose a department.',
  course_duration_invalid: 'Duration must be between 1 and 20 years.',
  course_semesters_invalid: 'Total semesters must be between 1 and 40.',
  course_code_taken: 'A course with this code already exists.',
  course_not_found: 'That course was not found.',
  course_in_use: 'This course is used by students or timetable settings, so it cannot be deleted.',
  courses_unavailable: 'The course list could not be loaded.',
  year_name_invalid: 'Enter an academic year name.',
  year_date_invalid: 'Enter a valid start and end date.',
  year_not_found: 'That academic year was not found.',
  year_in_use: 'This academic year is in use, so it cannot be deleted.',
  years_unavailable: 'The academic year list could not be loaded.',
  semester_name_invalid: 'Enter a semester name.',
  semester_number_invalid: 'Semester number must be between 1 and 20.',
  semester_date_invalid: 'Enter a valid start and end date.',
  semester_year_invalid: 'Choose an academic year.',
  semester_class_invalid: 'Choose a valid class, or leave it empty.',
  semester_credits_invalid: 'Check the credit range.',
  semester_not_found: 'That semester was not found.',
  semester_in_use: 'This semester is in use, so it cannot be deleted.',
  semesters_unavailable: 'The semester list could not be loaded.',
  batch_name_invalid: 'Enter a batch name.',
  batch_course_invalid: 'Choose a course.',
  batch_year_invalid: 'Choose a valid academic year, or leave it empty.',
  batch_range_invalid: 'Enter a valid start and end year.',
  batch_students_invalid: 'Student count must be between 0 and 10000.',
  batch_semester_invalid: 'Current semester must be between 1 and 40.',
  batch_not_found: 'That batch was not found.',
  batch_in_use: 'This batch is in use, so it cannot be deleted.',
  batches_unavailable: 'The batch list could not be loaded.',
  subject_name_invalid: 'Enter a subject name.',
  subject_code_invalid: 'Enter a subject code up to 20 characters.',
  subject_course_invalid: 'Choose a course.',
  subject_class_invalid: 'Choose a valid class, or leave it empty.',
  subject_semester_invalid: 'Choose a semester that belongs to this course.',
  subject_type_invalid: 'Choose a valid subject type.',
  subject_mode_invalid: 'Choose Theory, Practical, or Both.',
  subject_credits_invalid: 'Check the credits, marks, and weekly hours.',
  subject_url_invalid: 'Syllabus link must be an http or https address.',
  subject_not_found: 'That subject was not found.',
  subject_in_use: 'This subject is in use, so it cannot be deleted.',
  subjects_unavailable: 'The subject list could not be loaded.',
  allocation_faculty_invalid: 'Choose a faculty member.',
  allocation_subject_invalid: 'Choose a subject.',
  allocation_class_invalid: 'Choose a valid class, or leave it empty.',
  allocation_division_invalid: 'Choose a valid division, or leave it empty.',
  allocation_semester_invalid: 'Choose a valid semester, or leave it empty.',
  allocation_batch_invalid: 'Choose a valid batch, or leave it empty.',
  allocation_hours_invalid: 'Allocated hours must be between 0 and 80.',
  allocation_workload_invalid: 'Workload must be between 0 and 100.',
  allocation_type_invalid: 'Choose a valid allocation type.',
  allocation_date_invalid: 'Enter a valid start and end date.',
  allocation_not_found: 'That allocation was not found.',
  allocation_in_use: 'This allocation is in use, so it cannot be deleted.',
  allocations_unavailable: 'The allocation list could not be loaded.',
  holiday_name_invalid: 'Enter a holiday name.',
  holiday_program_invalid: 'Choose UG, PG, or Both.',
  holiday_day_invalid: 'Choose a day for a weekly holiday.',
  holiday_date_invalid: 'Choose a holiday date.',
  holiday_taken: 'A recurring holiday for this day and program already exists.',
  holiday_not_found: 'That holiday was not found.',
  holidays_unavailable: 'The holiday list could not be loaded.',
  academics_unavailable: 'The academic hub could not be loaded.',
  student_name_invalid: 'Enter a student name up to 100 characters.',
  student_username_invalid: 'Enter a username up to 50 characters.',
  student_password_invalid: 'Enter a password up to 128 characters.',
  student_email_invalid: 'Enter a valid email address.',
  student_phone_invalid: 'Phone must be 20 characters or fewer.',
  student_roll_invalid: 'Roll number must be 50 characters or fewer.',
  student_course_invalid: 'Choose a course.',
  student_class_invalid: 'Choose a valid class, or leave it empty.',
  student_division_invalid: 'Choose a valid division, or leave it empty.',
  student_username_taken: 'That username is already in use.',
  student_email_taken: 'That email is already registered for a student.',
  student_search_invalid: 'Search must be 100 characters or fewer.',
  student_ids_invalid: 'Choose at least one student.',
  student_not_found: 'That student was not found.',
  students_unavailable: 'The student list could not be loaded.',
  faculty_name_invalid: 'Enter a name up to 100 characters.',
  faculty_username_invalid: 'Enter a username up to 50 characters.',
  faculty_password_invalid: 'Enter a password up to 128 characters.',
  faculty_email_invalid: 'Enter a valid email address.',
  faculty_phone_invalid: 'Phone must be 20 characters or fewer.',
  faculty_designation_invalid: 'Designation must be 50 characters or fewer.',
  faculty_employee_invalid: 'Employee ID must be 20 characters or fewer.',
  faculty_department_invalid: 'Choose a department.',
  faculty_username_taken: 'That username is already in use.',
  faculty_email_taken: 'That email is already registered for a faculty member.',
  faculty_employee_taken: 'That employee ID is already in use.',
  faculty_search_invalid: 'Search must be 100 characters or fewer.',
  faculty_ids_invalid: 'Choose at least one faculty member.',
  faculty_not_found: 'That faculty member was not found.',
  faculty_unavailable: 'The faculty list could not be loaded.',
  workspace_unavailable: 'The page could not be loaded.',
  users_unavailable: 'The page could not be loaded.',
  roles_unavailable: 'The page could not be loaded.',
  permissions_unavailable: 'The page could not be loaded.',
  role_not_found: 'That role was not found.',
  role_name_invalid: 'Enter a role name up to 50 characters.',
  role_description_invalid: 'Description must be 400 characters or fewer.',
  role_level_invalid: 'Hierarchy level must be a number from 1 to 99.',
  role_name_taken: 'A role with this name already exists.',
  role_name_locked: 'The Super Admin role cannot be renamed.',
  permission_ids_invalid: 'Choose permissions from the list.',
  permission_name_invalid: 'Use a name like courses_view_course, up to 50 characters.',
  permission_module_invalid: 'Enter a module name up to 50 characters.',
  permission_description_invalid: 'Description must be 200 characters or fewer.',
  permission_name_taken: 'That permission name already exists.',
  invitations_unavailable: 'The page could not be loaded.',
  audit_unavailable: 'The page could not be loaded.',
  settings_unavailable: 'The page could not be loaded.',
  timetable_unavailable: 'The page could not be loaded.',
  attendance_unavailable: 'The page could not be loaded.',
  reports_unavailable: 'The page could not be loaded.',
  report_type_invalid: 'Choose a report.',
  report_filters_invalid: 'Check the report filters.',
  report_generate_failed: 'The report could not be generated.',
  report_not_found: 'That report was not found.',
  export_kind_invalid: 'Choose an export.',
  export_filters_invalid: 'Check the export filters.',
  export_unavailable: 'The export could not be queued.',
  shifts_unavailable: 'The page could not be loaded.',
  shift_request_invalid: 'Choose approve or reject.',
  proxy_unavailable: 'The page could not be loaded.',
  devices_unavailable: 'The page could not be loaded.',
  account_unavailable: 'The page could not be loaded.',
  account_email_invalid: 'Enter a valid email address.',
  account_phone_invalid: 'Phone must be 20 characters or fewer.',
  account_bio_invalid: 'Bio must be 500 characters or fewer.',
  account_address_invalid: 'Address must be 500 characters or fewer.',
  account_birth_invalid: 'Enter a valid birth date.',
  account_photo_invalid: 'Profile photo must be a PNG, JPG, or GIF.',
  portal_unavailable: 'The page could not be loaded.',
  portal_missing: 'Faculty profile not found.',
  portal_invalid: 'Check the form and try again.',
  portal_denied: 'You do not have permission to do that.',
  portal_date: 'Enter a valid date.',
  account_password_invalid: 'Enter the current password and a new password of 8 to 128 characters.',
  password_policy: 'The password does not meet the security policy.',
  password_expired: 'Change your password to continue.',
  security_policy_unavailable: 'Apply the database upgrade before saving the security policy.',
  security_policy_invalid: 'Check the security policy and try again.',
  security_policy_lockout: 'Include the network you are using, or leave the list empty.',
  license_required: 'A valid license is required before this can be added.',
  license_students: 'The license does not allow another student.',
  license_institutions: 'The license does not allow another institution.',
  branding_scope_unavailable: 'Apply the database upgrade before saving branding for one institution.',
  branding_institution: 'That institution is not available.',
  admin_network: 'Sign-in is not allowed from this network.',
  session_idle: 'Your session timed out. Sign in again.',
  account_password_mismatch: 'The current password is incorrect.',
  teacher_unavailable: 'The page could not be loaded.',
  student_unavailable: 'The page could not be loaded.',
  user_username_invalid: 'Enter a username of 3 to 50 characters.',
  user_password_invalid: 'Enter a password of 8 to 128 characters.',
  user_role_invalid: 'Choose a valid role.',
  user_status_invalid: 'Choose a valid status.',
  user_username_taken: 'That username is already in use.',
  user_email_taken: 'That email is already in use.',
  user_not_found: 'That user was not found.',
  user_protected: 'That account cannot be changed this way.',
  user_permission_invalid: 'Choose a permission.',
  user_permission_failed: 'That permission could not be changed.',
  user_group_invalid: 'Choose a permission group.',
  user_bulk_invalid: 'Choose users and an action.',
  invite_name_invalid: 'Enter a name up to 100 characters.',
  invite_email_invalid: 'Enter a valid email address.',
  invite_role_invalid: 'Choose Teacher or Student.',
  invite_duplicate: 'A pending invitation already exists for this email.',
  invite_registered: 'This email is already registered.',
  invite_not_found: 'That invitation was not found.',
  invite_used: 'A used invitation cannot be sent again.',
  settings_invalid: 'Check the branding fields and try again.',
  settings_file_invalid: 'Logos must be PNG, JPG, GIF, or SVG.',
  audit_not_found: 'That audit record was not found.',
  audit_session_invalid: 'That session could not be revoked.',
  timetable_selection_invalid: 'Choose a course, class, and division.',
  timetable_generate_failed: 'The timetable could not be generated.',
  timetable_targets_empty: 'No class with a faculty allocation matches that choice.',
  timetable_too_many: 'More than 1000 classes match. Generate one course at a time.',
  timetable_job_not_found: 'That generation was not found.',
  shift_request_missing: 'That request was not found.',
  availability_invalid: 'The availability could not be accepted.',
  availability_selection_invalid: 'Select at least one faculty member and one day.',
  availability_save_failed: 'The availability could not be saved.',
  proxy_filters_invalid: 'Enter a valid date range.',
  proxy_missing: 'That proxy request was not found.',
  proxy_closed: 'This request has already been decided.',
  proxy_choice_required: 'Choose the faculty who will take this class.',
  proxy_choice_invalid: 'Choose a faculty member who can take this subject.',
  proxy_busy: 'That faculty already has a class at this time.',
  proxy_note_invalid: 'The note must be 200 characters or less.',
  shift_name_invalid: 'Enter a shift name up to 80 characters.',
  shift_code_invalid: 'Enter a shift code using letters, numbers, _ or -.',
  shift_time_invalid: 'Enter a start and end time.',
  shift_order_invalid: 'Shift order must be between 1 and 99.',
  shift_in_use: 'This shift is assigned to faculty, so it cannot be deleted.',
  shift_save_failed: 'The shift could not be saved.',
  device_id_invalid: 'Enter a device ID using letters, numbers, . _ or -.',
  device_rate_invalid: 'Rate limit must be between 10 and 1000 requests per minute.',
  device_save_failed: 'The device could not be saved.',
  device_missing: 'That device was not found.',
  faculty_absence_invalid: 'Enter a date and a reason up to 200 characters.',
  faculty_absence_missing: 'That absence was not found.',
  faculty_absence_processed: 'A processed absence cannot be deleted.',
  faculty_proxy_missing: 'That proxy record was not found.',
  attendance_date_invalid: 'Enter a valid date.',
  attendance_status_invalid: 'Status must be Present, Absent, or Late.',
  attendance_record_missing: 'That attendance record was not found.',
  attendance_filters_invalid: 'Check the filters and try again.',
  attendance_limit_invalid: 'Choose between 1 and 500 logs.',
  bookings_unavailable: 'Room bookings could not be loaded.',
  bookings_table_missing: 'The bookings table is missing; apply the database migrations first.',
  booking_title_invalid: 'Give the booking a title of up to 120 characters.',
  booking_notes_invalid: 'Notes may be up to 500 characters.',
  booking_kind_invalid: 'Choose event, exam, maintenance or external.',
  booking_when_invalid: 'Give either a date or a weekday for the booking.',
  booking_time_invalid: 'Enter start and end times with the end after the start.',
  booking_room_invalid: 'That room is not available to this institution.',
  booking_room_busy: 'That room is timetabled at that time.',
  booking_room_booked: 'That room is already booked at that time.',
  booking_not_found: 'That booking was not found.',
  booking_not_owned: 'Only the institution that owns the room can decide this booking.',
  booking_decided: 'That booking has already been decided.',
  booking_filter_invalid: 'The filter is not valid.',
  norms_unavailable: 'Workload norms could not be loaded.',
  terms_unavailable: 'Academic terms could not be loaded.',
  term_invalid: 'Give a name, a kind and dates inside the academic year.',
  term_overlap: 'Those dates overlap another term for this institution.',
  term_not_found: 'That term was not found.',
  terms_table_missing: 'The academic terms table is missing; apply the database migrations first.',
  syllabus_unavailable: 'The syllabus tables are missing; apply the database migrations first.',
  assessment_unavailable: 'The assessment tables are missing; apply the database migrations first.',
  assessment_invalid: 'Check the component, outcome or mapping and try again.',
  assessment_marks_invalid: 'Marks must be from 0 up to the component maximum, with at most one decimal place.',
  assessment_locked: 'That component is locked. Unlock it before changing marks or the scheme.',
  assessment_in_use: 'A locked component still uses an outcome you are removing.',
  assessment_import_invalid: 'The file needs a header row with roll_number and marks.',
  exam_unavailable: 'The exam tables are missing; apply the database migrations first.',
  exam_invalid: 'Check the exam name, dates, subjects and rooms, then try again.',
  exam_not_found: 'That exam was not found.',
  exam_no_students: 'A paper has no students. Check the cohort and, for an elective, the subject selections.',
  exam_no_room: 'Choose at least one room with seats.',
  exam_no_invigilator: 'There is no active faculty member who can invigilate.',
  exam_unsolved: 'No exam timetable fits those rooms, the seating gap and invigilator availability.',
  syllabus_invalid: 'Each unit needs a number from 1 to 99, a title and planned hours from 0.5 to 400.',
  syllabus_in_use: 'A lesson has been logged against a unit you are removing.',
  lesson_invalid: 'Choose a unit and a topic, and hours between 0.5 and 3.',
  lesson_unit: 'That unit is not part of this subject.',
  norms_invalid: 'Norms are hours per week from 0 to 60, with the minimum no higher than the maximum.',
  capability_off: 'This feature is switched off for your institution.',
  second_factor_unavailable: 'Second factor is not available until the database migration is applied.',
  second_factor_invalid: 'That code was not accepted.',
  second_factor_enrolled: 'An authenticator is already set up. Use a current code to replace it.',
  second_factor_required: 'Your role must keep an authenticator app.',
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  /** The server's error object as sent (code, message and any extras such as `alternatives`); treat as untrusted. */
  readonly details: Record<string, unknown>

  constructor(message: string, status: number, code = '', details: Record<string, unknown> = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

type Envelope<T> =
  | { success: true; data: T }
  | { success: false; error?: { code?: string; message?: string; [key: string]: unknown } }

function messageFor(status: number, code: string): string {
  if (code && errorMessages[code]) return errorMessages[code]
  if (status === 401) return errorMessages.unauthorized
  if (status === 403) return errorMessages.forbidden
  return 'The request could not be completed.'
}

async function parseEnvelope<T>(response: Response): Promise<T> {
  let body: unknown
  try {
    body = await response.json()
  } catch {
    throw new ApiError(messageFor(response.status, ''), response.status)
  }

  if (!body || typeof body !== 'object' || !('success' in body)) {
    throw new ApiError(messageFor(response.status, ''), response.status)
  }

  const envelope = body as Envelope<T>
  if (envelope.success) return envelope.data
  const code = envelope.error?.code || ''
  throw new ApiError(messageFor(response.status, code), response.status, code, envelope.error && typeof envelope.error === 'object' ? envelope.error : {})
}

function sameOriginApiPath(path: string): string {
  if (!path.startsWith('/api/') || path.startsWith('//') || path.includes('..') || path.includes('\\') || path.includes('://')) {
    throw new ApiError('The request was blocked.', 0, 'blocked')
  }
  return path
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(sameOriginApiPath(path), {
      ...init,
      credentials: 'include',
      cache: 'no-store',
      headers: { Accept: 'application/json', ...init.headers },
    })
  } catch {
    throw new ApiError('The Flask server is not reachable. Start it on port 5000 and try again.', 0, 'unreachable')
  }

  try {
    return await parseEnvelope<T>(response)
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.code === 'session_idle' || error.code === 'admin_network') window.location.assign('/')
      throw error
    }
    throw new ApiError(messageFor(response.status, ''), response.status)
  }
}

export function apiGet<T>(path: string): Promise<T> {
  return apiRequest<T>(path)
}
