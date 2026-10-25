# سامانه بازرگانی رویش

**شناسه سامانه: `commerce` — شماره ۳ از سه سامانه رویش.** این پوشه بک‌اند مشتریان، خدمات نرم‌افزاری، پیشنهاد قیمت، قرارداد پروژه، صورتحساب و دریافت وجه است. [پرسنلی](../personnel/README.md) و [انبار](../inventory/README.md) سرویس‌های جدا هستند.

پس از نصب اولیه با `setup.cmd` در ریشه، فایل [start.cmd](start.cmd) همین پوشه را اجرا کنید؛ فقط بازرگانی و رابط آن شروع می‌شوند. فرمان معادل از ریشه: `python scripts/manage.py start --service commerce`. رابط: http://localhost:3003 و API: http://localhost:8003/docs.

| منبع | مسیر |
| --- | --- |
| قواعد و گردش کامل بازرگانی | [راهنمای تفصیلی](README.fa.md) |
| رابط مخصوص بازرگانی | [راهنمای فرانت‌اند](../../frontend/README.md)؛ فرمان `npm run dev:commerce` در پوشه frontend |
| قرارداد API | [commerce.json](../../docs/openapi/commerce.json) |
| آزمون‌های اختصاصی | [test_commerce.py](../../tests/test_commerce.py) |
| راهنمای معماری | [Word ۱](../../deliverables/word-guides/03-commerce/commerce-01-architecture.docx) |
| دیاگرام و طراحی دیتابیس | [Word ۲](../../deliverables/word-guides/03-commerce/commerce-02-database.docx) |
| ساختار بک‌اند | [Word ۳](../../deliverables/word-guides/03-commerce/commerce-03-backend.docx) |
| ساختار فرانت‌اند | [Word ۴](../../deliverables/word-guides/03-commerce/commerce-04-frontend.docx) |
| کاربری و API | [Word ۵](../../deliverables/word-guides/03-commerce/commerce-05-user-api.docx) |

مدل‌ها در `models.py`، اعتبارسنجی‌ها در `schemas.py` و مسیرها و قواعد کسب‌وکار در `app.py` هستند. دیتابیس پیش‌فرض `data/commerce.db` است؛ برای PostgreSQL از `COMMERCE_DATABASE_URL` استفاده کنید. مبالغ صحیح تومان و تاریخ‌های ورودی میلادی‌اند. ثبت دریافت، وجهی در بانک جابه‌جا نمی‌کند.

[گزارش ممیزی بازرگانی](AUDIT.fa.md) · [بازگشت به معرفی کل پروژه](../../README.md)
