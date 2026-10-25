# رابط های مستقل سه سامانه رویش

این پوشه سورس مشترک React و Next.js را نگه می‌دارد؛ هر سامانه با پورت، تنظیم، حساب و API مستقل اجرا می‌شود. فایل‌های رابط برای جلوگیری از تکرار کد در یک پوشه‌اند و اطلاعات سه سامانه را به هم ادغام نمی‌کنند.

| سامانه | فرمان توسعه در همین پوشه | فرمان production پس از build | رابط | بک‌اند اختصاصی |
| --- | --- | --- | --- | --- |
| **پرسنلی** | `npm run dev:personnel` | `npm run start:personnel` | http://localhost:3001 | [services/personnel](../services/personnel/README.md) |
| **انبار** | `npm run dev:inventory` | `npm run start:inventory` | http://localhost:3002 | [services/inventory](../services/inventory/README.md) |
| **بازرگانی** | `npm run dev:commerce` | `npm run start:commerce` | http://localhost:3003 | [services/commerce](../services/commerce/README.md) |

نصب اولیه از ریشه با `setup.cmd` انجام می‌شود. برای اجرای API و رابط یک سامانه با هم، `start.cmd` داخل پوشه همان سامانه را اجرا کنید. فایل تعریف بخش‌ها `src/lib/resources.ts`، عملیات وضعیت `src/lib/workflows.ts`، فرم‌ها `src/components/ResourceForm.tsx` و ارتباط شبکه `src/lib/api.ts` هستند. `ROYESH_SYSTEM` و `API_URL` نمونه اجراشده را تعیین می‌کنند.

[راهنمای کامل ساختار و تنظیم فرانت‌اند](README.fa.md) · [معرفی کل پروژه](../README.md)
