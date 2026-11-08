# Timetable Management documentation

These notes describe the application as it runs now: a React screen on port 5173 and a Flask API on port 5000, with MySQL behind the API.

| Document | What it covers |
| --- | --- |
| [application.md](application.md) | Who uses the system, how a request travels, and which addresses are public |
| [modules.md](modules.md) | The frontend, JSON API, services, security, and data folders |
| [system-flows.md](system-flows.md) | Sign-in, invitations, timetable generation, exports, and attendance |
| [DATABASE.md](DATABASE.md) | Supported server, Alembic revisions, adopting an existing database, and the rules for new revisions |

`route_inventory.md` is an older generated list of Flask URLs. Some of those paths still exist as legacy views. The browser uses the React routes and `/api` described in the files above.
