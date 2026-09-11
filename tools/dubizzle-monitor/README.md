# مراقب إعلانات دوبيزل (Dubizzle Car Monitor)

أداة تراقب صفحات بحث السيارات على dubizzle.com، وترسل إشعار فوري (إيميل + واتساب)
لكل إعلان جديد يطابق الشروط.

## كيف تشتغل

- GitHub Actions يشغّل `monitor.py` كل 10 دقائق تلقائيًا (وممكن تشغّله يدويًا).
- السكربت يفتح كل رابط بحث في `watchlist.json` عن طريق متصفح حقيقي (Playwright/Chromium)،
  يجمع الإعلانات، ويقارنها مع `state/seen.json` (قائمة الإعلانات اللي شافها قبل).
- أي إعلان جديد (id مو موجود بالقائمة) ويطابق فلاتر السنة/السعر ← إشعار فوري.
- أول تشغيل لأي بحث جديد **لا يرسل إشعارات** لكل الإعلانات الموجودة حاليًا، بس يسجلها
  كنقطة بداية (baseline)، وبعدين يبلغك بس عن الجديد فعلاً.

## ⚠️ تحذير مهم قبل ما تعتمد عليها

اختبرت الوصول لـ dubizzle.com من هذا السيرفر، ولقيت إن الموقع محمي بنظام حماية من
البوتات اسمه **Imperva** (صفحة "Pardon Our Interruption"). هذا النظام أحيانًا يحجب
الطلبات القادمة من عناوين IP تخص خوادم سحابية (زي اللي يستخدمها GitHub Actions)، حتى
لو استخدمنا متصفح حقيقي (Playwright) بدل طلب HTTP عادي.

بمعنى: **احتمال يشتغل تمام من أول مرة، واحتمال يصير محجوب من طرف GitHub Actions تحديدًا.**
بعد ما تفعّل الأداة، راقب أول كم تشغيلة من تبويب Actions بالمستودع (GitHub → Actions →
Dubizzle Car Monitor) وشوف اللوق. إذا شفت رسالة `blocked by anti-bot protection`
بشكل متكرر، الحل:

1. **تشغيلها من جهازك/سيرفر خاص فيك** بدل GitHub Actions (نفس الكود، بس تشغّله بـ cron
   على جهازك أو VPS بدل الجدولة على GitHub) — عناوين IP العادية أقل عرضة للحجب.
2. أو **استخدام بروكسي** (residential proxy service) — أقدر أضيف دعم له بسرعة إذا احتجناه.

قلّي إذا صار عندك حجب متكرر وأساعدك تبدّل الطريقة.

## الإعداد (خطوة بخطوة)

### 1. إعداد الإيميل (Gmail)

1. فعّل "2-Step Verification" على حساب Gmail حقك (من إعدادات الأمان بحساب Google).
2. روح لـ https://myaccount.google.com/apppasswords وسوّي App Password جديد (اختر
   اسم مثل "dubizzle-monitor")، وانسخ الكود المكوّن من 16 حرف.
3. بالمستودع على GitHub: **Settings → Secrets and variables → Actions → New repository secret**
   وضيف:
   - `GMAIL_ADDRESS` = إيميلك (مثال: alhajkhalil77@gmail.com)
   - `GMAIL_APP_PASSWORD` = الكود اللي نسخته (بدون مسافات)
   - `NOTIFY_EMAIL_TO` = الإيميل اللي تبي يوصله الإشعار (ممكن نفس `GMAIL_ADDRESS`)

### 2. إعداد واتساب (CallMeBot)

1. من واتساب حقك، ضيف الرقم `+34 644 59 71 67` كجهة اتصال.
2. أرسل له رسالة نصها بالضبط: `I allow callmebot to send me messages`
3. راح يردّك ببوت برسالة فيها API Key (رقم). خذه.
4. بالمستودع على GitHub: ضيف Secrets:
   - `CALLMEBOT_PHONE` = رقمك مع رمز الدولة بدون + ولا مسافات (مثال: 971501234567)
   - `CALLMEBOT_APIKEY` = الكود اللي وصلك

### 3. تفعيل الجدولة

الـ workflow موجود بـ `.github/workflows/dubizzle-monitor.yml` ومفعّل تلقائيًا بمجرد
ما تدمج/تدفع هذا الفرع لفرع رئيسي يشتغل عليه GitHub Actions (عادة `main`). تقدر أيضًا
تشغّله يدويًا فورًا للتجربة: **Actions → Dubizzle Car Monitor → Run workflow**.

## إضافة/تعديل أنواع السيارات

عدّل ملف `watchlist.json`. كل عنصر بالقائمة = بحث واحد:

```json
{
  "name": "اسم وصفي تعطيه للبحث (يظهر بالإشعار)",
  "url": "رابط نتائج البحث من dubizzle.com (انسخه من المتصفح بعد ما تطبّق فلتر الماركة/الموديل)",
  "min_year": 2021,
  "max_year": 2027,
  "min_price": null,
  "max_price": null,
  "max_pages": 2
}
```

- `url`: افتح uae.dubizzle.com، اختر الماركة والموديل من قائمة السيارات (بدون لا تحدد سعر
  ولا مدينة عشان يغطي كل الإمارات وكل الأسعار)، وانسخ رابط الصفحة كما هو.
- `min_year` / `max_year` / `min_price` / `max_price`: خليها `null` إذا ما تبي فلترة، أو رقم
  إذا تبي تحديد نطاق. الفلترة تصير من جهتنا (بعد ما نجمع الإعلانات) مو من رابط دوبيزل نفسه.
- `max_pages`: كم صفحة نتائج يفحص بكل تشغيلة (2 كافية غالبًا لأن الفحص كل 10 دقايق).

المثال الحالي بالملف: تويوتا C-HR موديل 2021 إلى 2027، أي سعر، كل الإمارات.

لإضافة نوع سيارة ثاني، ضيف عنصر جديد بنفس القائمة (array) بنفس الشكل.

## تشغيل تجريبي على جهازك (اختياري، للتأكد قبل الاعتماد على GitHub Actions)

```bash
cd tools/dubizzle-monitor
pip install -r requirements.txt
playwright install chromium
export GMAIL_ADDRESS=... GMAIL_APP_PASSWORD=... NOTIFY_EMAIL_TO=...
export CALLMEBOT_PHONE=... CALLMEBOT_APIKEY=...
python monitor.py
```
