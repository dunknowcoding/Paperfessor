<div align="center">

<h1>
  <img src="../../assets/Prof_Meerk.png" width="88" alt="البروفيسور ميرك — تميمة Paperfessor" valign="middle"/>
  &nbsp;Paperfessor
</h1>

**تُدخِل اتجاه بحث واحدًا، فتحصل على مراجعة أدبيات وتجارب حقيقية وورقة بحثية بتنسيق المؤتمرات.**

[![License: MIT](https://img.shields.io/badge/License-MIT-2E5E4E.svg)](../../LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-33475B.svg)](../../pyproject.toml)

[English](../../README.md) · [简体中文](../zh-CN/README.md) · [日本語](../ja/README.md) · [Español](../es/README.md) · [Français](../fr/README.md) · [Deutsch](../de/README.md) · [Italiano](../it/README.md) · [Português](../pt/README.md) · [Русский](../ru/README.md) · [한국어](../ko/README.md) · **العربية**

<img src="../../assets/Meerk_studio.png" alt="استوديو البروفيسور ميرك: وكيل الدكتوراه يصوغ الأفكار والورقة، ووكيل الماجستير يراجع الأدبيات، ووكيل البرمجة ينفّذ التجارب" width="92%"/>

*داخل استوديو البروفيسور ميرك — عقول فضولية + معرفة مشتركة + تكرار دؤوب = أثر حقيقي.*

</div>

---

<div dir="rtl">

Paperfessor مساعد بحثي مكوَّن من ثلاثة وكلاء يعمل على جهازك وبمفتاح API
الخاص بك. أعطه اتجاه بحث (تكفي جملة واحدة) فيعمل فريق الوكلاء كمختبر صغير:

</div>

| الوكيل | الدور | واجهة الحالة |
|---|---|---|
| 🎓 **طالب الدكتوراه** | يبتكر الطريقة، يوزّع المهام، يشرف، يكتب الورقة ويفحصها | `planning / dispatching / monitoring / reviewing / writing / archiving` |
| 📚 **طالب الماجستير** | بحث أدبيات واسع (arXiv + OpenAlex + Scholar)، قراءة كاملة دقيقة، استخراج الأدلة | `websearch / reading / analyzing / reporting / idle / stopped` |
| 💻 **طالب البكالوريوس** | ينفّذ الطريقة وفق عقد صارم، يحمّل البيانات الحقيقية ويعالجها، يجري التجارب بعدة بذور | `coding / thinking / reporting / idle / stopped` |

<div dir="rtl">

كل رقم في الورقة **مقاس ولا يُختلق أبدًا**: مجموعات البيانات تنزيلات عامة
حقيقية (تُرفض البيانات الاصطناعية)، والطريقة المقترحة تُتحقق بتشغيلها فعلًا،
وكل صفحة من ملف PDF تجتاز فحص تخطيط آليًا قبل قبول التشغيل.

## التثبيت

</div>

```bash
# Python 3.11+
pip install -e ".[gui]"
# أو بعد النشر:
pip install paperfessor[gui]
```

<div dir="rtl">

يوصى بتثبيت LaTeX (‏TeX Live/MiKTeX مع `acmart`) لإخراج PDF؛ وبدونه يعود
البرنامج إلى `.docx` (‏pandoc) أو Markdown.

## الإعداد الأول

تُحفظ مفاتيح API في **حلقة مفاتيح نظام التشغيل** — لا على القرص ولا في
السجلات ولا في الورقة.

</div>

```bash
paperfessor key set minimax --key "sk-..."
paperfessor key test minimax
paperfessor models list
```

<div dir="rtl">

## توليد ورقة

</div>

```bash
paperfessor run "anomaly detection in multivariate time series"
```

<div dir="rtl">

النتائج في `workspace/`: ملف `paper/body/paper.pdf` (بتنسيق المؤتمرات)،
و`src/results/results.json` (مقاييس مقاسة، k = 3 بذور، متوسط ± فاصل ثقة
95٪)، وأشكال حقيقية، وسجلات عمل الوكلاء. تفضّل نافذة رسومية؟ شغّل
`paperfessor-gui`.

## الاستخدام المسؤول وإخلاء المسؤولية

بُني Paperfessor **لأغراض البحث فقط**.

- **لا** تقدّم مخرجاته بوصفها عملك الخاص غير المُعان إلى المؤتمرات أو
  المجلات أو المقررات؛ التزم بسياسات الجهة المستهدفة بشأن مساعدة الذكاء
  الاصطناعي والتأليف والانتحال، وأفصح عن مساعدة الذكاء الاصطناعي حيثما
  يُطلب ذلك.
- **تحقق من كل شيء.** يجب أن يراجع إنسانٌ النصوص والاستشهادات والشيفرة
  والأرقام المولَّدة قبل أي استخدام حقيقي.
- **لا** تستخدمه للبحوث المفبركة أو التلاعب بالاستشهادات أو «مصانع
  الأوراق» أو أي غرض غير قانوني أو مضلِّل.

**لا يتحمل مؤلفو هذا المستودع والمساهمون فيه أي مسؤولية عن إساءة استخدام
هذا البرنامج أو عن أي عواقب ناتجة عن استخدامه.**

## الترخيص

[MIT](../../LICENSE). تميمة البروفيسور ميرك جزء من هوية المستودع.

</div>
