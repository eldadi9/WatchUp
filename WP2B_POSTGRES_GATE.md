# ⁧WatchUp WP-2B — שער בידוד PostgreSQL⁩

## ⁧החלטה⁩

⁧**PASS** לתשתית המקומית והסטטית של PostgreSQL.⁩

⁧**NOT GO** עדיין לפריסה ב־VPS, לחיבור WhatsApp חי, לטלפון של יולי או לנתונים אמיתיים.⁩

## ⁧מה הושלם⁩

- ⁧Schema ייעודי: `watchup`.⁩
- ⁧תפקידי `watchup_owner`, ‏`watchup_migrator` ו־`watchup_app` ללא Login וללא `BYPASSRLS`.⁩
- ⁧ביטול הרשאות `PUBLIC` והרשאות יצירת אובייקטים מהיישום.⁩
- ⁧הרשאות CRUD מינימליות ליישום.⁩
- ⁧`ENABLE ROW LEVEL SECURITY` וגם `FORCE ROW LEVEL SECURITY`.⁩
- ⁧מדיניות tenant מחייבת עבור קריאה וכתיבה באמצעות `USING` ו־`WITH CHECK`.⁩
- ⁧כשל סגור כאשר tenant חסר, ריק או שונה.⁩
- ⁧בדיקת UTF-8 והגדרת `Asia/Jerusalem` קבועה למסד.⁩
- ⁧13 מתוך 13 בדיקות מקומיות עברו.⁩

## ⁧מגבלת האישור⁩

⁧במחשב המקומי אין `psql` או Docker. לכן הבדיקות מאמתות את קבצי SQL והמדיניות, אך אינן הוכחה שהמיגרציה ורמת הבידוד רצו בפועל על שרת PostgreSQL.⁩

## ⁧חובה לפני מידע אמיתי⁩

1. ⁧להקים Database ייעודי ל־WatchUp על PostgreSQL נתמך ומעודכן.⁩
2. ⁧להריץ את המיגרציה כ־PostgreSQL cluster administrator מורשה.⁩
3. ⁧ליצור משתמשי בדיקה מוגבלים ללא הרשאות ניהול.⁩
4. ⁧להוכיח בפועל ש־tenant אחד אינו יכול לקרוא, להוסיף, לעדכן או למחוק מידע של tenant אחר.⁩
5. ⁧להוכיח שהיישום אינו יכול ליצור Schema, לשנות RLS או לעבור לתפקיד ניהולי.⁩
6. ⁧לבנות Adapter של PostgreSQL; ה־API הנוכחי עדיין משתמש ב־SQLite מקומי.⁩
7. ⁧לגזור tenant מהקשר משתמש מאומת בשרת ולא מה־payload הנכנס.⁩
8. ⁧לבצע Revalidation של Valdi לאחר בדיקות PostgreSQL אמיתיות.⁩

## ⁧מצב מידע⁩

⁧לא חובר טלפון, לא נקלט מידע של יולי, לא הוגדרו credentials ולא בוצע שינוי ב־VPS.⁩
