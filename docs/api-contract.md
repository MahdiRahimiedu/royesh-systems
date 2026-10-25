# API contract for implementation

All backends expose /api/v1 and /health, /docs, /openapi.json. Ports personnel 8001, inventory 8002, commerce 8003. Each service imports shared Python utilities from `shared` and runs from repository root: python -m uvicorn services.personnel.app:app --port 8001.

## Shared API
POST /api/v1/auth/login JSON {username,password} returns {access_token,token_type:"bearer",user:{id,username,full_name,role}}. GET /api/v1/auth/me; POST /api/v1/auth/logout; POST /api/v1/auth/change-password {current_password,new_password}. GET /api/v1/users (admin), POST /api/v1/users {username,full_name,password,role,employee_id?}, PATCH /api/v1/users/{id} {full_name?,role?,is_active?}. Roles admin, manager, staff. Local seed admin/admin12345, manager/manager12345, staff/staff12345 only if SEED_DEMO=true (default local). Tokens bearer with server-side expiry/revocation. GET /api/v1/audit-logs (manager/admin) paged. GET /api/v1/dashboard returns {metrics:[{label,value,unit?}], recent:[{title,subtitle,status,date}], notices:[{title,detail}]}.

List endpoints return {items:[],total,page,page_size}; params q, page=1,page_size=20. Status filter where relevant. POST returns full created object, PATCH updates allowed fields. Money JSON integer toman. Dates ISO YYYY-MM-DD; datetimes ISO UTC. Errors HTTPException detail Persian string or Pydantic array. All writes auth; business managers admin/manager except own leave/missions and own profile. Staff read only permitted records; employee_id scope where relevant. Referential IDs UUID strings. Each item includes id, created_at, updated_at where applicable. No hard deletion of transaction history.

## Personnel endpoints
- /departments: name,description ; list/create/patch
- /employees: personnel_code,first_name,last_name,email,phone,department_id?,job_title,employment_type(full_time/part_time/contract),hire_date,status(active/inactive/terminated),base_salary; list/create/patch; list output full_name and department_name; staff self only. GET /employees/lookup limited fields for integration read.
- /employment-contracts: employee_id,title,start_date,end_date?,base_salary,status(active/ended),notes
- /leaves: employee_id,type(annual/sick/unpaid),start_date,end_date,reason,status(pending/approved/rejected); POST /{id}/decision {status,comment?}; staff own creation and read.
- /missions: employee_id,title,destination,start_date,end_date,allowance,reason,status(pending/approved/rejected); POST /{id}/decision {status,comment?,allowance?}; allowance is optional and accepted only when approving a mission.
- /adjustments: employee_id,kind(reward/penalty),amount,reason,date
- /payrolls: employee_id,period(YYYY-MM),base_salary,bonus,deduction,total,status(draft/paid); POST creation {employee_id,period,bonus:0,deduction:0} snapshots base and applicable adjustments; PATCH /{id} {bonus?,deduction?} corrects draft values and recomputes the snapshot total; POST /{id}/pay marks paid once. Paid rows immutable, staff own read.

## Inventory endpoints
- /items: sku,name,category,unit,tracking_type(quantity/serialized),min_stock,description; list/create/patch; output quantity_available and quantity_total computed
- /suppliers: name,contact_name,phone,email,address ; list/create/patch
- /purchases: supplier_id,item_id,quantity,unit_price,notes,status(pending/approved/received/cancelled); POST /{id}/approve {}, POST /{id}/receive {serial_numbers?:string[]} adds incoming movement and assets atomically; POST /{id}/cancel {}
- /movements: item_id,type(in/out),quantity,reason,reference?; GET and POST. For serialized items use purchases receive/assets not direct out; include serial_numbers optional for stock in.
- /assets: item_id,serial_number,status(available/assigned/retired),notes; list, create; PATCH /{id} notes/status only valid transitions; no duplicate serial
- /assignments: asset_id?,item_id?,employee_id,employee_name,quantity,notes; for asset fixed quantity 1; POST creates out/locks asset; POST /{id}/return {} records return, prevents double return. GET list.
Staff read inventory catalog only; manager/admin operational endpoints. GET /reports/stock return paged or {items,total,page,page_size}.

## Commerce endpoints
- /customers: name,company_name,contact_name,email,phone,address,status(active/inactive); list/create/patch
- /offerings: name,description,unit_price,unit(project/month/hour),is_active; list/create/patch
- /quotations: customer_id,title,valid_until,notes,lines:[{offering_id?,description,quantity,unit_price}],status(draft/sent/accepted/rejected),total; PATCH /{id} corrects draft-only fields/lines atomically; POST /{id}/status {status}; detail includes lines; create and update compute total
- /contracts: customer_id,quotation_id?,title,employee_id?,employee_name?,start_date,end_date?,amount,status(draft/active/completed/cancelled),notes; list/create/patch; quotation_id conversion must validate accepted/customer and prevent duplicate conversion. POST /{id}/status {status}
- /invoices: contract_id,issue_date,due_date,amount,description,status(unpaid/partial/paid/void),paid_amount,balance; list/create; POST /{id}/void {}; ensure sum invoices doesn't exceed contract amount ignoring void
- /payments: invoice_id,amount,paid_date,method(bank/cash/cheque),reference,notes; list/create; reject overpayment, idempotent reference uniqueness when nonempty, transactional invoice totals
- /reports/receivables return paged invoice rows with customer_name,contract_title,balance.
Staff commerce read-only except no sensitive user/audit admin features. Manager/admin all business writes.

## Shared Python utilities
`shared.database.make_database(service)` -> (engine, SessionLocal, Base); Base = shared.database.Base globally, build separate engine per service. `shared.models.Record` mixin includes id UUID, created_at, updated_at. Model mapped columns `Mapped`, `mapped_column`; inherit (Record, Base).
`shared.app.create_app(service,title,Base,engine,SessionLocal,seed_fn)` attaches db dependency `shared.database.get_db(request)` and auth router. `shared.auth.current_user` dependency; `shared.auth.require_manager` dependency (admin/manager); `shared.auth.require_admin`. Each independent server process imports its own domain models. Tests import all apps and use isolated databases; the extra unused domain tables in those test databases do not couple runtime services. Integrators should call the API rather than importing the other service's models.
`shared.audit.log_action(db,user,action,entity,entity_id,details="")` adds AuditLog without commit; caller commits. `shared.utils.paginate(db,statement,page,page_size)` returns list dict via `serialize(record)`; `shared.utils.serialize(record,**extra)` maps columns to JSON-safe Python values. For joined labels enrich manually.
Use `Depends(get_db)`, `Depends(require_manager)` etc. Standard SQLAlchemy sync Session. DB errors handled globally. `seed_fn(db)` runs after shared demo users created and must be idempotent. Seed admin/manager/staff employee_id can be set via querying shared.auth.User. Shared models User/AuditLog imported from shared.auth/shared.audit.

Calendar decisions (quotation expiry and future receipt dates) use BUSINESS_TIMEZONE, default Asia/Tehran. Stored timestamps are UTC. Employee links in personnel user accounts must refer to an existing employee; other systems hold a UUID reference until integration. OpenAPI snapshots are the machine-readable source of request schemas.
