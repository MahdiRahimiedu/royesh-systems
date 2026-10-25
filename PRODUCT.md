# Product
<!-- impeccable:product-schema 1 -->
## Platform
web
## Stack
Python backend and React/Next.js frontend requested by the user. Backend framework and implementation details delegated to the agent. FastAPI and SQLAlchemy selected for explicit, readable APIs. Local SQLite by default for an immediate laptop run; PostgreSQL supported for server deployment.
## Users
University students build and explain three independent systems for a software company: personnel, inventory, and commerce. Company staff are the simulated operational users.
## Product Purpose
Deliver working, understandable business software with persistent data, permissions, forms, business workflows and documented APIs. A separate team will integrate the three systems.
## Operating Context
Run locally on the user's Windows laptop today. Deployment online must remain possible. Each backend and frontend instance must run independently of other systems.
## Capabilities and Constraints
Personnel: employees, employment contracts, leave, missions, payroll, rewards and deductions. Inventory: equipment and consumables, purchases, suppliers, movements, assignments and returns. Commerce: customers, services, quotations, project contracts, invoices and receipts. No live payment gateway or legal payroll compliance requested.
## Evidence on Hand
Two whiteboard photos and confirmed user clarifications recorded in docs/initial-analysis.fa.md. Third system is commerce per user's explicit confirmation. Seed records are fictional demonstration data and must be identified as such.
## Product Principles
Readable, conventional code. Independent data ownership. Real validations and durable transactions. Documentation sufficient for students and the integration team.
## Open Decisions and Assumptions
Persian RTL interface and example company name «رویش» are implementation assumptions. Local single-company use. No integration gateway or SSO in this delivery. User instructed the agent to proceed with design and implementation without further design confirmation.
