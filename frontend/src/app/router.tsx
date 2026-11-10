import { useEffect, useState } from 'react'
import { createBrowserRouter, Navigate } from 'react-router-dom'
import { RegisterPage } from '../features/auth/pages/RegisterPage'
import { MaintenancePage } from '../features/errors/MaintenancePage'
import { getBranding, getSession, type Branding } from '../shared/api/endpoints'
import { fallbackBranding } from '../shared/security/sanitize'
import { PortalProfilePage } from '../features/account/pages/PortalProfilePage'
import { AttendancePage, AttendanceRecordsPage, FacultyAttendancePage, MobileLogsPage, MyAttendancePage, SubjectAttendancePage } from '../features/attendance/pages/AttendancePage'
import { AuditFailedPage, AuditLogsPage, AuditPage, AuditSessionsPage } from '../features/audit/pages/AuditPage'
import { DevicesPage } from '../features/devices/pages/DevicesPage'
import { FacultyPage } from '../features/faculty/pages/FacultyPage'
import { FacultySessionsPage } from '../features/faculty/pages/FacultySessionsPage'
import { RoleHome } from '../features/home/RoleHome'
import { InvitationsPage } from '../features/invitations/pages/InvitationsPage'
import { MyProxyPage, ProxyPage } from '../features/proxy/pages/ProxyPage'
import { ReportsPage } from '../features/reports/pages/ReportsPage'
import { PermissionsPage } from '../features/roles/pages/PermissionsPage'
import { RoleAssignmentsPage, RolePermissionsPage, RolesPage } from '../features/roles/pages/RolesPage'
import { AvailabilityPage, MyAvailabilityPage, MyShiftsPage, ShiftRequestsPage, ShiftsPage } from '../features/shifts/pages/ShiftsPage'
import { StudentsPage } from '../features/students/pages/StudentsPage'
import { AttendanceHistoryPage, MarkAttendancePage } from '../features/teacher/pages/FacultyPortal'
import { AssignmentsPage } from '../features/teacher/pages/AssignmentsPage'
import { MyClassesPage, MyWeekPage } from '../features/teacher/pages/TeacherHome'
import { GeneratePage, TimetablePage } from '../features/timetable/pages/TimetablePage'
import { TimetableRulesPage } from '../features/timetable/pages/TimetableRulesPage'
import { TimetableVersionsPage } from '../features/timetable/pages/TimetableVersionsPage'
import { WorkloadNormsPage } from '../features/timetable/pages/WorkloadNormsPage'
import { UsersPage } from '../features/users/pages/UsersPage'
import { UserPermissionsPage } from '../features/users/pages/UserPermissionsPage'
import { AllocationsPage } from '../features/academics/pages/AllocationsPage'
import { BatchesPage } from '../features/academics/pages/BatchesPage'
import { HolidaysPage } from '../features/academics/pages/HolidaysPage'
import { LabBatchesPage } from '../features/academics/pages/LabBatchesPage'
import { SemestersPage } from '../features/academics/pages/SemestersPage'
import { SubjectsPage } from '../features/academics/pages/SubjectsPage'
import { TermsPage } from '../features/academics/pages/TermsPage'
import { SyllabusPage } from '../features/academics/pages/SyllabusPage'
import { AssessmentPage } from '../features/academics/pages/AssessmentPage'
import { ExamDutiesPage } from '../features/academics/pages/ExamDutiesPage'
import { ExamsPage } from '../features/academics/pages/ExamsPage'
import { InternalsRoute } from '../features/academics/pages/PortalAssessmentPage'
import { YearsPage } from '../features/academics/pages/YearsPage'
import { CoursesPage } from '../features/courses/pages/CoursesPage'
import { DepartmentsPage } from '../features/departments/pages/DepartmentsPage'
import { BookingsPage } from '../features/rooms/pages/BookingsPage'
import { RoomsPage } from '../features/rooms/pages/RoomsPage'
import { CapabilitiesPage } from '../features/settings/pages/CapabilitiesPage'
import { InstitutionsPage } from '../features/settings/pages/InstitutionsPage'
import { IntegrationsPage } from '../features/settings/pages/IntegrationsPage'
import { NotificationSettingsPage } from '../features/settings/pages/NotificationSettingsPage'
import { SecurityPolicyPage } from '../features/settings/pages/SecurityPolicyPage'
import { SettingsPage } from '../features/settings/pages/SettingsPage'
import { LegacyRedirect, LegacyStaffAlias, PrefixedRedirect } from './LegacyRedirect'
import { ErrorPage } from '../features/errors/ErrorPage'
import { RootGate } from './SessionGate'

function RegisterGate() {
  const [maintenance, setMaintenance] = useState<boolean | null>(null)
  const [branding, setBranding] = useState<Branding>(fallbackBranding)
  useEffect(() => {
    const institutionCode = new URLSearchParams(window.location.search).get('i') || ''
    void Promise.all([getSession(), getBranding(institutionCode).catch(() => fallbackBranding)])
      .then(([session, nextBranding]) => {
        setBranding(nextBranding)
        setMaintenance(session.maintenance)
      })
      .catch(() => setMaintenance(false))
  }, [])
  if (maintenance === null) return <div className="min-h-screen bg-gray-100" />
  if (maintenance) return <MaintenancePage branding={branding} />
  return <RegisterPage />
}

export const router = createBrowserRouter([
  { path: '/register/:token', element: <RegisterGate /> },
  {
    path: '/',
    element: <RootGate />,
    children: [
      { index: true, element: <RoleHome /> },
      { path: 'account', element: <PortalProfilePage /> },
      { path: 'profile', element: <PortalProfilePage /> },
      { path: 'admin/login', element: <Navigate to="/admin" replace /> },
      {
        path: 'admin',
        children: [
          { index: true, element: <RoleHome /> },
          { path: 'rooms', element: <RoomsPage /> },
          { path: 'rooms/bookings', element: <BookingsPage /> },
          { path: 'departments', element: <DepartmentsPage /> },
          { path: 'courses', element: <CoursesPage /> },
          { path: 'academics', element: <Navigate to="/admin/academic-years" replace /> },
          { path: 'academic-years', element: <YearsPage /> },
          { path: 'academic-terms', element: <TermsPage /> },
          { path: 'academic-syllabus', element: <SyllabusPage /> },
          { path: 'academic-assessments', element: <AssessmentPage /> },
          { path: 'academic-exams', element: <ExamsPage /> },
          { path: 'semesters', element: <SemestersPage /> },
          { path: 'subjects', element: <SubjectsPage /> },
          { path: 'batches', element: <BatchesPage /> },
          { path: 'lab-batches', element: <LabBatchesPage /> },
          { path: 'allocations', element: <AllocationsPage /> },
          { path: 'holidays', element: <HolidaysPage /> },
          { path: 'students', element: <StudentsPage /> },
          { path: 'faculty', element: <FacultyPage /> },
          { path: 'faculty/:facultyId', element: <FacultySessionsPage /> },
          { path: 'users', element: <UsersPage /> },
          { path: 'users/:userId/permissions', element: <UserPermissionsPage /> },
          { path: 'permissions', element: <PermissionsPage /> },
          { path: 'roles', element: <RolesPage /> },
          { path: 'roles/:roleId/users', element: <RoleAssignmentsPage /> },
          { path: 'roles/:roleId', element: <RolePermissionsPage /> },
          { path: 'invitations', element: <InvitationsPage /> },
          { path: 'settings', element: <SettingsPage /> },
          { path: 'settings/notifications', element: <NotificationSettingsPage /> },
          { path: 'settings/integrations', element: <IntegrationsPage /> },
          { path: 'settings/institutions', element: <InstitutionsPage /> },
          { path: 'settings/capabilities', element: <CapabilitiesPage /> },
          { path: 'settings/security', element: <SecurityPolicyPage /> },
          { path: 'audit', element: <AuditPage /> },
          { path: 'audit/logs', element: <AuditLogsPage /> },
          { path: 'audit/sessions', element: <AuditSessionsPage /> },
          { path: 'audit/failed-logins', element: <AuditFailedPage /> },
          { path: 'timetable', element: <TimetablePage /> },
          { path: 'timetable/generate', element: <GeneratePage /> },
          { path: 'timetable/rules', element: <TimetableRulesPage /> },
          { path: 'timetable/versions', element: <TimetableVersionsPage /> },
          { path: 'timetable/workload', element: <WorkloadNormsPage /> },
          { path: 'attendance', element: <AttendancePage /> },
          { path: 'attendance/manage', element: <AttendanceRecordsPage /> },
          { path: 'attendance/faculty', element: <FacultyAttendancePage /> },
          { path: 'attendance/mobile', element: <MobileLogsPage /> },
          { path: 'reports', element: <ReportsPage /> },
          { path: 'reports/*', element: <Navigate to="/admin/reports" replace /> },
          { path: 'shifts', element: <ShiftsPage /> },
          { path: 'shifts/requests', element: <ShiftRequestsPage /> },
          { path: 'shifts/availability', element: <AvailabilityPage /> },
          { path: 'proxy', element: <ProxyPage /> },
          { path: 'devices', element: <DevicesPage /> },
          { path: '*', element: <LegacyStaffAlias />, handle: { errorPage: true } },
        ],
      },
      { path: 'rooms', element: <PrefixedRedirect /> },
      { path: 'departments', element: <PrefixedRedirect /> },
      { path: 'courses', element: <PrefixedRedirect /> },
      { path: 'academics', element: <Navigate to="/admin/academic-years" replace /> },
      { path: 'academic-years', element: <PrefixedRedirect /> },
      { path: 'semesters', element: <PrefixedRedirect /> },
      { path: 'subjects', element: <PrefixedRedirect /> },
      { path: 'batches', element: <PrefixedRedirect /> },
      { path: 'lab-batches', element: <PrefixedRedirect /> },
      { path: 'allocations', element: <PrefixedRedirect /> },
      { path: 'holidays', element: <PrefixedRedirect /> },
      { path: 'students', element: <PrefixedRedirect /> },
      { path: 'faculty', element: <PrefixedRedirect /> },
      { path: 'faculty/:facultyId', element: <PrefixedRedirect /> },
      { path: 'users', element: <PrefixedRedirect /> },
      { path: 'users/:userId/permissions', element: <PrefixedRedirect /> },
      { path: 'permissions', element: <PrefixedRedirect /> },
      { path: 'roles', element: <PrefixedRedirect /> },
      { path: 'roles/:roleId/users', element: <PrefixedRedirect /> },
      { path: 'roles/:roleId', element: <PrefixedRedirect /> },
      { path: 'invitations', element: <PrefixedRedirect /> },
      { path: 'settings', element: <PrefixedRedirect /> },
      { path: 'audit/*', element: <PrefixedRedirect /> },
      { path: 'audit', element: <PrefixedRedirect /> },
      { path: 'timetable/*', element: <PrefixedRedirect /> },
      { path: 'timetable', element: <PrefixedRedirect /> },
      { path: 'attendance/*', element: <PrefixedRedirect /> },
      { path: 'attendance', element: <PrefixedRedirect /> },
      { path: 'reports/*', element: <PrefixedRedirect /> },
      { path: 'reports', element: <PrefixedRedirect /> },
      { path: 'shifts/*', element: <PrefixedRedirect /> },
      { path: 'shifts', element: <PrefixedRedirect /> },
      { path: 'proxy', element: <PrefixedRedirect /> },
      { path: 'devices', element: <PrefixedRedirect /> },
      { path: 'my-timetable', element: <MyWeekPage /> },
      { path: 'my-classes', element: <MyClassesPage /> },
      { path: 'my-assignments', element: <AssignmentsPage /> },
      { path: 'my-shifts', element: <MyShiftsPage /> },
      { path: 'my-availability', element: <MyAvailabilityPage /> },
      { path: 'my-proxy', element: <MyProxyPage /> },
      { path: 'my-internals', element: <InternalsRoute /> },
      { path: 'my-duties', element: <ExamDutiesPage /> },
      { path: 'my-attendance', element: <MyAttendancePage /> },
      { path: 'my-attendance/mark/:timetableId', element: <MarkAttendancePage /> },
      { path: 'my-attendance/history/:timetableId', element: <AttendanceHistoryPage /> },
      { path: 'my-attendance/:subjectId', element: <SubjectAttendancePage /> },
      { path: 'login', element: <LegacyRedirect /> },
      { path: 'teacher', element: <LegacyRedirect /> },
      { path: 'teacher/*', element: <LegacyRedirect /> },
      { path: 'student', element: <LegacyRedirect /> },
      { path: 'student/*', element: <LegacyRedirect /> },
      { path: 'profile/*', element: <LegacyRedirect /> },
      { path: '*', element: <ErrorPage status={404} />, handle: { errorPage: true } },
    ],
  },
])
