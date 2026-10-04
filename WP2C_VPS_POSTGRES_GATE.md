# ⁧WatchUp WP-2C — שער PostgreSQL מבודד ב־VPS⁩

## ⁧החלטה⁩

⁧**GO** לבסיס PostgreSQL המבודד של WatchUp ב־VPS.⁩

⁧**NOT GO** עדיין ל־API ב־Production, לחיבור WhatsApp חי, לטלפון של יולי או למידע אמיתי.⁩

## ⁧הבידוד שהוקם⁩

- ⁧Container ייעודי: `watchup-postgres`, PostgreSQL ‏16.15.⁩
- ⁧רשת Docker פנימית ייעודית: `watchup-internal`.⁩
- ⁧אין Port שמפורסם לשרת או לאינטרנט.⁩
- ⁧Volume ייעודי: `watchup-postgres-data`.⁩
- ⁧סוד הניהול נשמר בקובץ root בהרשאת `600` ומורכב ל־Container לקריאה בלבד.⁩
- ⁧Database ייעודי: `watchup`, קידוד UTF-8 ואזור זמן `Asia/Jerusalem`.⁩
- ⁧Schema, Roles והרשאות ייעודיים; RLS מופעלת וכפויה.⁩
- ⁧`watchup_app` יכול להתחבר רק ל־Database של WatchUp בתוך ה־Cluster.⁩
- ⁧ההקמה הזמנית הוסרה מה־PostgreSQL המשותף; אין בו Database או Roles של WatchUp.⁩

## ⁧בדיקות התנהגות⁩

⁧`test_rls.sql` הורץ ב־VPS עם `ON_ERROR_STOP` בתוך Transaction שבסופו `ROLLBACK`. הבדיקה הוכיחה:⁩

1. ⁧tenant חסר או ריק לא רואה מידע.⁩
2. ⁧tenant תקין רואה רק את הרשומה שלו.⁩
3. ⁧Update ו־Delete של tenant אחר משפיעים על 0 רשומות.⁩
4. ⁧מנהל הבדיקה אישר שהרשומה של tenant האחר נשארה ללא שינוי.⁩
5. ⁧Insert ל־tenant אחר נדחה.⁩
6. ⁧משתמש היישום אינו יכול ליצור Schema או להפוך ל־Owner.⁩
7. ⁧לא נשארו אירועים או Login סינתטי לאחר הבדיקה.⁩

## ⁧Valdi⁩

⁧PASS לבידוד ה־Container, הרשת, ה־Volume, ה־Database, ה־ACL וה־RLS. Valdi בדק בקריאה בלבד ואישר גם את תקינות מבנה בדיקת ההתנהגות.⁩

## ⁧נותר לפני מידע אמיתי⁩

- ⁧Adapter של PostgreSQL ל־API עם tenant שנגזר מזהות מאומתת בשרת.⁩
- ⁧Application Login ייעודי וסוד נפרד בהרשאות `watchup_app` בלבד.⁩
- ⁧תוכנית גיבוי ושחזור ובדיקת Restore.⁩
- ⁧חיבור API ו־Bridge ברשת הפנימית בלבד.⁩
- ⁧Valdi נוסף לאחר חיבור ה־API ולפני חיבור הטלפון.⁩

## ⁧מצב מידע⁩

⁧אין מידע אמיתי, אין חיבור לטלפון, אין Pairing ואין מסלול WhatsApp חי.⁩
