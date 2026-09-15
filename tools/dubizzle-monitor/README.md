# مراقب إعلانات دوبيزل (Dubizzle Car Monitor)

أداة تراقب صفحات بحث السيارات على dubizzle.com، وترسل إشعار فوري (إيميل + واتساب)
لكل إعلان جديد يطابق الشروط.

## كيف تشتغل

- GitHub Actions يشغّل `monitor.py` كل 10 دقائق تلقائيًا (وممكن تشغّله يدويًا).
- السكربت يفتح كل رابط بحث في `watchlist.json` عن طريق **ScraperAPI** (خدمة خارجية تجيب
  محتوى الصفحة نيابة عنا)، يجمع الإعلانات، ويقارنها مع `state/seen.json` (قائمة الإعلانات
  اللي شافها قبل).
- أي إعلان جديد (id مو موجود بالقائمة) ويطابق فلاتر السنة/السعر/الكلمة ← إشعار فوري.
- أول تشغيل لأي بحث جديد **لا يرسل إشعارات** لكل الإعلانات الموجودة حاليًا، بس يسجلها
  كنقطة بداية (baseline)، وبعدين يبلغك بس عن الجديد فعلاً.

## ⚠️ ليش نستخدم ScraperAPI بدل ما نتصل بدوبيزل مباشرة

جرّبنا الوصول لـ dubizzle.com مباشرة من GitHub Actions (بمتصفح حقيقي Playwright كمان)،
وانحجبنا فعليًا — الموقع محمي بنظام حماية بوتات اسمه **Imperva**، وطلع بكل تشغيلة:
`blocked by anti-bot protection`. هذا لأن عناوين IP حق GitHub Actions معروفة/محجوبة.

الحل: نمرر الطلبات عبر **ScraperAPI** (خدمة متخصصة بالضبط بهذي المشكلة — عناوين IP
متنوعة + تجاوز أنظمة الحماية)، فالكود الحين يطلب الصفحة من خلالها بدل ما يتصل بدوبيزل نفسه.

### ملاحظة عن التكلفة

ScraperAPI فيها تجربة مجانية (عادة كذا آلاف طلب)، وبعدها خطط شهرية بسيطة. بما إن عندنا
9 بحثات × تشغيلة كل 10 دقايق × احتمال صفحتين لكل بحث، هذا استهلاك مو قليل. لو حسّيت
التكلفة عالية بعد ما تخلص التجربة المجانية، تقدر:
- تقلّل عدد الصفحات لكل بحث (`max_pages` بملف `watchlist.json`، خليها 1 بدل 2)
- أو تبعّد فترة الفحص (بملف `.github/workflows/dubizzle-monitor.yml`، غيّر
  `cron: "*/10 * * * *"` لمثلاً `"*/20 * * * *"` = كل 20 دقيقة)

راجع صفحة الأسعار على موقع ScraperAPI قبل ما تقرر، والأسعار تتغيّر مع الوقت.

## الإعداد (خطوة بخطوة)

### 0. إعداد ScraperAPI (ضروري، بدونه الفحص ما يشتغل أبدًا)

1. روح لـ https://www.scraperapi.com وسوّي حساب مجاني (Sign Up).
2. بعد التسجيل بتوصل للوحة التحكم (Dashboard)، وبتشوف **API Key** ظاهر — انسخه.
3. بالمستودع على GitHub: **Settings → Secrets and variables → Actions → New repository secret**
   وضيف:
   - `SCRAPERAPI_KEY` = الكود اللي نسخته

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
  "keyword": null,
  "max_pages": 2
}
```

- `url`: افتح uae.dubizzle.com، اختر الماركة والموديل من قائمة السيارات (بدون لا تحدد سعر
  ولا مدينة عشان يغطي كل الإمارات وكل الأسعار)، وانسخ رابط الصفحة كما هو.
- `min_year` / `max_year` / `min_price` / `max_price`: خليها `null` إذا ما تبي فلترة، أو رقم
  إذا تبي تحديد نطاق. الفلترة تصير من جهتنا (بعد ما نجمع الإعلانات) مو من رابط دوبيزل نفسه.
- `keyword`: كلمة لازم تكون موجودة بنص الإعلان عشان يتقبل (بدون حساسية لحالة الأحرف). مفيدة
  للموديلات اللي مالها صفحة منفصلة على دوبيزل، زي **Hybrid** — مثلاً "Camry Hybrid" ما له
  رابط مستقل، فنستخدم رابط "Camry" العادي + `"keyword": "hybrid"` عشان نطلع بس النسخة الهايبرد.
  خليها `null` إذا ما تبي فلترة كلمة معينة.
- `max_pages`: كم صفحة نتائج يفحص بكل تشغيلة (2 كافية غالبًا لأن الفحص كل 10 دقايق).

**المثال الحالي بالملف** (9 بحثات، كلها موديل 2021-2027، أي سعر، كل الإمارات):
- Toyota C-HR (كل النسخ)
- Toyota Camry Hybrid فقط
- Toyota RAV4 Hybrid فقط
- Toyota Corolla Hybrid فقط
- Toyota Corolla Cross Hybrid فقط
- Hyundai Accent
- Hyundai Elantra
- Kia Picanto
- Kia Cerato

لإضافة نوع سيارة ثاني (ماركة ثانية مثلاً)، ضيف عنصر جديد بنفس القائمة (array) بنفس الشكل.

## تشغيل تجريبي على جهازك (اختياري، للتأكد قبل الاعتماد على GitHub Actions)

```bash
cd tools/dubizzle-monitor
pip install -r requirements.txt
export SCRAPERAPI_KEY=...
export GMAIL_ADDRESS=... GMAIL_APP_PASSWORD=... NOTIFY_EMAIL_TO=...
export CALLMEBOT_PHONE=... CALLMEBOT_APIKEY=...
python monitor.py            # فحص كامل
python monitor.py --test     # يرسل إشعار تجريبي فورًا (بدون ما يلمس دوبيزل)
```
