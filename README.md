# Royal Tee Stitches

Bespoke Nigerian fashion website with a working order/measurement form that emails submissions (with reference image attached) straight to the shop.

## Structure
```
royal-tee-stitches/
├── app.py                 # Flask backend (routes, upload handling, SMTP email)
├── requirements.txt
├── .env.example           # copy to .env and fill in real values
├── templates/
│   ├── index.html          # home page
│   └── order.html          # tabbed measurement order form
└── static/uploads/         # temp storage for reference images (auto-cleared)
```

## Run locally
```bash
pip install -r requirements.txt
cp .env.example .env        # then edit .env with your Gmail App Password
python app.py
```
Visit http://localhost:5000

## Email setup (free, Resend)
1. Sign up at https://resend.com and create an API key.
2. Add it to `.env` as `RESEND_API_KEY`.
3. Verify a sending domain at https://resend.com/domains (or, for quick
   testing only, use `onboarding@resend.dev` as `MAIL_FROM` — see the
   comments at the bottom of `.env.example`).
4. All orders submitted via the form will be emailed to `MAIL_TO`
   (defaults to oladokuntaiye26@gmail.com), formatted as HTML tables
   grouped by Customer Info / Blouse / Skirt / Gown / Trouser, with the
   uploaded reference image attached.

Prefer Gmail SMTP instead? Swap `send_order_email()` in `app.py` back to
`smtplib` — happy to provide that version if needed.

## Notes
- Uploaded images are saved temporarily to `static/uploads/`, attached to
  the email, then deleted — nothing is kept on disk after sending.
- The order form submits via `fetch()` to `/submit-order` and shows a toast
  notification on success or failure, without a full page reload.
- All measurement fields are optional except Full Name and Phone Number —
  customers only fill the garment tabs relevant to their order.
