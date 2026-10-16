# ⁧WatchUp — ארכיטקטורה מוצעת⁩

## ⁧סטטוס החלטה⁩

⁧עודכן 08/10/2026: זהו מסמך יעד לצד מצב קיים. ה־QR הקיים עובד; pairing חדש נשאר כפוף ל־Security Gate. ממשק ה־POC הקיים הוא HTML/JavaScript סטטי, וה־API הקיים הוא Python HTTP server — React/Next ו־FastAPI הם כיוון עתידי, לא תיאור המימוש הנוכחי. הפערים והשלבים הבאים נמצאים ב־`ROADMAP.md`.⁩

## ⁧עקרונות⁩

- ⁧מופע WhatsApp אחד עבור יולי בלבד.⁩
- ⁧בידוד מלא מכל Bridge אחר ב־VPS.⁩
- ⁧הפרדה בין קליטה גולמית, עיבוד עסקי ותצוגת הורה.⁩
- ⁧קריאה בלבד נאכפת בקוד ובתשתית.⁩
- ⁧מספר מינימלי של רכיבים ל־POC.⁩

## ⁧רכיבים⁩

### ⁧WhatsApp Bridge⁩

⁧קוד Go הקיים במצב WatchUp Read Only. בסביבת ה־VPS הפעילה Privacy Mode אינו שומר מסד bridge, מדיה או היסטוריה מתמשכת; כל שינוי בזה חייב לעבור מדיניות שמירה ומחיקה.⁩

### ⁧WatchUp Backend⁩

⁧המימוש הקיים הוא שירות Python HTTP; FastAPI הוא אפשרות עתידית בלבד. השירות אחראי לקליטת Webhook, אימות, deduplication, מנוע כללים, התראות ו־API לממשק.⁩

### ⁧PostgreSQL⁩

⁧container ייעודי ל־WatchUp עם database, user ו־volume נפרדים. שומר אירועים מנורמלים, כללים, התראות, משתמשים, דוחות ו־audit.⁩

### ⁧Web App / PWA⁩

⁧המימוש הקיים הוא ממשק HTML/JavaScript סטטי בעברית וב־RTL, מותאם תחילה לטלפון ומרענן את נתוני ה־API. React/Next.js ו־SSE/WebSocket הם אפשרות עתידית, לא מצב קיים.⁩

### ⁧Read-only MCP⁩

⁧שרת MCP הקיים לאחר הסרת כלי כתיבה. משמש את הסוכן לשאילתות בלבד ואינו משמש כצינור האירועים הראשי.⁩

## ⁧זרימת מידע⁩

```text
Yuli WhatsApp
  -> watchup-bridge
  -> signed internal webhook
  -> watchup-api
  -> PostgreSQL
  -> rules and alerts
  -> Hebrew PWA
```

⁧ה־MCP יקרא מידע רק מתוך מקורות WatchUp המבודדים. אין גישה ל־KitaBrief או למסד נתונים של פרויקט אחר.⁩

## ⁧פריסת VPS⁩

- ⁧Compose project: `watchup`.⁩
- ⁧Network פרטית: `watchup_internal`.⁩
- ⁧Containers: `watchup-bridge`,‏ `watchup-api`,‏ `watchup-web`,‏ `watchup-postgres`, ובהמשך `watchup-mcp`.⁩
- ⁧Bridge אינו מפרסם פורט לציבור; אבחון זמני בלבד דרך `127.0.0.1:8082`.⁩
- ⁧נתוני Bridge: `/opt/watchup/bridge/store`.⁩
- ⁧מדיה: `/opt/watchup/bridge/media`.⁩
- ⁧סודות: `/opt/watchup/secrets`.⁩
- ⁧נתוני PostgreSQL: volume ייעודי עם prefix של WatchUp.⁩
- ⁧גישה ציבורית רק ל־PWA/API דרך reverse proxy ו־TLS.⁩

## ⁧Read Only Defense in Depth⁩

1. ⁧מצב build או environment מפורש בשם `WATCHUP_READ_ONLY=true`.⁩
2. ⁧ה־Bridge מחזיר `403` עבור `/api/send`,‏ `/api/react` ו־`/api/typing`.⁩
3. ⁧כלי שליחה אינם נרשמים ב־MCP.⁩
4. ⁧ה־Backend אינו מקבל command שמייצג כתיבה ל־WhatsApp.⁩
5. ⁧בדיקות אוטומטיות מוכיחות שלא נקראת פונקציית `SendMessage`.⁩
6. ⁧Audit מתעד כל ניסיון כתיבה חסום בלי לשמור תוכן רגיש.⁩

## ⁧אמינות אירועים⁩

⁧Webhook קיים אינו מספיק. השדרוג המתוכנן יוסיף event ID, גרסת schema, timestamp, HMAC, retry עם backoff, תור עמיד ו־Dead Letter Queue. PostgreSQL יכול לשמש בתחילת הדרך כתור durable באמצעות טבלת inbox, ללא Redis.⁩

## ⁧החלטות פשטות ל־POC⁩

- ⁧אין n8n בנתיב הקריטי.⁩
- ⁧אין Redis בשלב ראשון.⁩
- ⁧אין Kubernetes.⁩
- ⁧אין multi-tenant.⁩
- ⁧אין אחסון ענן חיצוני למדיה.⁩
- ⁧התראות בתוך האפליקציה לפני Push.⁩

## ⁧פערים שדורשים Spike לפני Implementation מלא⁩

- ⁧אירוע אמין של איש קשר חדש או חסר.⁩
- ⁧אירועי הוספה, הצטרפות ויציאה מקבוצה.⁩
- ⁧מיקום וסוגי מדיה שאינם נשלחים כיום במלואם ב־Webhook.⁩
- ⁧התנהגות history sync של הטלפון של יולי.⁩
- ⁧יציבות Linked Device במשך שבעה ימים.⁩

## ⁧החלטת Git הנדרשת⁩

⁧המלצה: לשמור את `whatsapp-mcp` כ־fork עצמאי ולחבר אותו כ־Git submodule, משום שהוא קוד צד שלישי עם היסטוריה ועדכונים משלו. אין לבצע זאת עד Owner GO למימוש.⁩

## ⁧תיקון מסלול ההתראה — 06/10/2026⁩

1. ⁧ה־Bridge פותר את השולח מול מאגר אנשי הקשר ומעביר `is_recognized`;‏ `PushName` נשאר תווית תצוגה בלבד.⁩
2. ⁧ה־Backend שומר עד 30 מילות מעקב לכל `tenant_id` ו־`child_id` במסד הקיים, באמצעות שאילתות פרמטריות ובאותה מחיקה משפחתית.⁩
3. ⁧ה־Dashboard API מחזיר את המילים והאירועים; הממשק מסווג ומציג התראות מאותו חוזה ומרענן כל 15 שניות. אין תור נוסף ואין שירות Push בשלב ה־POC.⁩
4. ⁧הדפדפן מפעיל קול והתראת מערכת רק אחרי לחיצה מפורשת שמאפשרת Audio/Notification. הממשק מציין שהאפליקציה צריכה להישאר פתוחה.⁩
5. ⁧סנכרון הקבוצות נשאר snapshot מוגבל ל־80 משתתפים; אין קריאה נוספת ל־WhatsApp מלחיצה על קבוצה.⁩
