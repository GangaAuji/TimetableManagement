# How the application works

The Timetable Management System is the college workspace for people, teaching setup, timetables, attendance, and reports. Staff run the college from the admin area. Teachers and students use a smaller portal for their own classes.

## People and homes

| Role | Sign-in | Home |
| --- | --- | --- |
| Student | `/` or `/login` | `/` then My timetable and Attendance |
| Teacher | `/` or `/login` | `/` then classes, shifts, proxy, and attendance |
| Admin, Super Admin, HOD | `/admin/login` | `/admin` |

`/` is the student and teacher sign-in when nobody is signed in. An admin address such as `/admin/students` shows the admin sign-in until an admin account is signed in. After an admin signs in, `/` sends them to `/admin`.

The sidebar only lists pages the account is allowed to open. Super Admin can open every staff page. Other staff accounts need the matching permission. Teachers and students cannot open `/admin` pages.

## Two processes

```text
Browser
  -> Vite on 127.0.0.1:5173
       serves the React app
       proxies /api, /login, /admin/login, /register, and /logout to Flask
  -> Flask on 127.0.0.1:5000
       JSON under /api
       sign-in posts under /login and /admin/login
       mobile sync under /mobile-sync/v1
  -> MySQL
```

`app.py` starts Flask through `create_app()` in `app_factory.py`. The React router lives in `frontend/src/app/router.tsx`. `RootGate` in `SessionGate.tsx` decides whether to show a sign-in form or the signed-in shell.

## What a signed-in request does

1. The page asks `GET /api/session` and `GET /api/branding`.
2. If the session is empty, the sign-in form stays on screen.
3. If the session is present, `page-access.ts` checks the role and permission for that path.
4. The page calls `/api/...`. The API requires a signed-in account, then the route checks the permission or role it already required.
5. The route calls a service. The service reads or writes MySQL.
6. The JSON response is `{ success, data }` or `{ success, error: { code, message } }`.

## Addresses that stay open

These are the only JSON reads that work without a session. They exist so the sign-in page and an invitation link can render.

| Call | Purpose |
| --- | --- |
| `GET /api/branding` | College name, colors, and logos for the sign-in screen |
| `GET /api/csrf-token` | Token required before a sign-in or other write |
| `GET /api/session` | `{ authenticated: false }` or the current account summary |
| `GET /api/register/<token>` | Whether an invitation is open, used, or expired |

Sign-in itself is `POST /login` for students and teachers and `POST /admin/login` for staff. Registration is `POST /register/<token>`. Everything else under `/api` returns 401 until a session exists.

Writes also need the security token, a same-origin browser request, and a JSON body. Profile photos and settings uploads are the multipart exceptions. Public sign-in and registration are rate limited, and signed-in API calls have a higher per-account limit.

## Legacy Flask pages

Older Flask views under `/admin`, `/teacher`, and `/student` are still registered. A browser GET for those pages is turned into the React route by `ui/pages.py`. The React app is the interface people use. Mobile devices use `/mobile-sync/v1` and are separate from `/api`.
