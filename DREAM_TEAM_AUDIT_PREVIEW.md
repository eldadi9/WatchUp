# ⁧WatchUp — Dream Team Audit ו־Preview⁩

## ⁧תוצאה⁩

- ⁧תאריך: 2026-10-04.⁩
- ⁧ה־Audit וה־Preview רצו במצב קריאה בלבד.⁩
- ⁧אימות לפני ואחרי: לא נכתב ולא השתנה קובץ בפרויקט.⁩
- ⁧סיווג: פרויקט קיים ונקי ללא Dream Team קודם.⁩
- ⁧החלטת הכלי: נדרשת התקנה.⁩
- ⁧התנגשויות Dream Team: אין.⁩
- ⁧מצב הפעלה מתוכנן: MANUAL.⁩
- ⁧מצב אוטונומי בטוח: כבוי.⁩
- ⁧לא יתבצעו commit, push או deploy.⁩

## ⁧זהות מוצעת⁩

- Project name: `WatchUp`
- Project id: `watchup`
- Ori id: `watchup-orchestrator`
- Trigger: `watchup`
- Engine version: `0.1.0`
- Bootstrap version: `1.1`

## ⁧ליבת הפרויקט שתיווצר ב־Apply⁩

- `.dream-team/project.json`
- `.dream-team/ENGINE_VERSION`
- `.dream-team/engine-config.json`
- `.dream-team/BOOTSTRAP_VERSION`
- `.dream-team/learning/`
- `.ai/andy/current.json`
- `CLAUDE.md`
- `.claude/skills/watchup-orchestrator/SKILL.md`

⁧קבצים קיימים לשינוי בשלב הליבה: אין. קבצים למחיקה: אין.⁩

## ⁧Preview של ספקי העבודה⁩

- Claude Code: ⁧17 רשומות התקנה חדשות.⁩
- Codex: ⁧11 קבצים חדשים ושני בלוקים מנוהלים למיזוג בתוך `AGENTS.md`.⁩
- Cursor: ⁧22 קבצים חדשים ושני בלוקים מנוהלים למיזוג בתוך `AGENTS.md`.⁩
- ⁧בסך הכול: 54 רשומות התקנה ו־49 יעדים ייחודיים.⁩
- ⁧היעד הקיים היחיד שנדרש למיזוג הוא `AGENTS.md`; אין להחליף אותו.⁩
- ⁧הגדרות Claude ימוזגו אל `.claude/settings.json`.⁩
- ⁧בלוקי Claude ימוזגו אל `CLAUDE.md` לאחר יצירתו.⁩

## ⁧Skills של הליבה⁩

⁧שלוש חבילות קנוניות חדשות יתווספו בשלמותן בלי לשנות את 12 החבילות הקיימות:⁩

- `.agents/skills/andy`
- `.agents/skills/yuli-ceo`
- `.agents/skills/valdi-validator`

## ⁧ממצאים והגנות⁩

- ⁧לא נמצא Ori כפול או Dream Team ישן.⁩
- ⁧Valdi מוגדר כמבקר עצמאי לקריאה בלבד ואינו מתקן בעצמו.⁩
- ⁧רק Gate רשאי להחליט GO או NO-GO.⁩
- ⁧מצב למידה אינו רשאי לשנות את המערכת בשקט.⁩
- ⁧Grok אינו נכלל ב־Apply הראשון.⁩
- ⁧תיקיית Git קיימת, אך כלי ה־Audit דיווח שאינו מזהה repository בגלל בעיית ownership של סביבת ההרצה. ההתקנה תשתמש ב־snapshot עצמאי ולא תבצע פעולת Git.⁩
- ⁧ב־New Project Tool קיים שינוי מקומי קודם בקובץ בדיקה; לא ניגע בו ולא נכניס אותו לפרויקט.⁩

## ⁧שער Apply⁩

⁧Apply יבוצע רק לאחר אישור Owner מפורש. לפני הכתיבה תיווצר תמונת גיבוי, ולאחריה יבוצעו אימות hashes, בדיקת Ori יחיד, בדיקת שימור `AGENTS.md` והרצה שנייה שחייבת להיות NO-OP.⁩
