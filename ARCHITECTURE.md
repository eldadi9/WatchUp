# ⁧WatchUp — ארכיטקטורה מוצעת⁩

## ⁧סטטוס החלטה⁩

⁧ארכיטקטורה מוצעת לאישור. אין לפרוס או לחבר QR לפני Security Gate ו־Deployment GO.⁩

## ⁧עקרונות⁩

- ⁧מופע WhatsApp אחד עבור יולי בלבד.⁩
- ⁧בידוד מלא מכל Bridge אחר ב־VPS.⁩
- ⁧הפרדה בין קליטה גולמית, עיבוד עסקי ותצוגת הורה.⁩
- ⁧קריאה בלבד נאכפת בקוד ובתשתית.⁩
- ⁧מספר מינימלי של רכיבים ל־POC.⁩

## ⁧רכיבים⁩

### ⁧WhatsApp Bridge⁩

⁧קוד Go הקיים, לאחר הוספת מצב WatchUp Read Only. שומר session והיסטוריה גולמית ב־SQLite ומעביר אירועים ל־Backend.⁩

### ⁧WatchUp Backend⁩

⁧שירות Python/FastAPI מומלץ ל־POC. אחראי לקליטת Webhook, אימות HMAC, תור אירועים, deduplication, מנוע כללים, התראות, דוחות ו־API לממשק.⁩

### ⁧PostgreSQL⁩

⁧container ייעודי ל־WatchUp עם database, user ו־volume נפרדים. שומר אירועים מנורמלים, כללים, התראות, משתמשים, דוחות ו־audit.⁩

### ⁧Web App / PWA⁩

⁧יישום React/Next.js בעברית וב־RTL, מותאם תחילה לטלפון. מקבל עדכונים חיים מה־Backend באמצעות SSE או WebSocket.⁩

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

