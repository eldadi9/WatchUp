# ⁧WP-3 — שער פריסת דשבורד ל־VPS⁩

## ⁧תוצאה⁩

**PASS — ⁧דשבורד ההדגמה זמין ב־HTTPS.⁩**

## ⁧כתובת⁩

`https://watchup.srv1282987.hstgr.cloud/`

## ⁧בידוד ואבטחה⁩

- ⁧Container נפרד: `watchup-web`.⁩
- ⁧אין Port ציבורי ל־container; הגישה עוברת דרך Traefik בלבד.⁩
- ⁧מערכת הקבצים של ה־container היא לקריאה בלבד.⁩
- ⁧Capabilities הוסרו למעט המינימום הנדרש ל־Nginx.⁩
- ⁧נוספו CSP, חסימת iframe, חסימת camera/microphone/location ומדיניות referrer.⁩
- ⁧אין חיבור ל־PostgreSQL, ל־WatchUp API או ל־WhatsApp.⁩

## ⁧גבול זמני⁩

⁧האתר ציבורי משום שהוא מכיל נתוני הדגמה בלבד. לפני חיבור מידע אמיתי חובה להוסיף Authentication והרשאות הורה, ולהעביר את ה־Frontend לחיבור API מאומת.⁩

