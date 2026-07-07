# Automatic Security Updates & Mail Notifications

How to verify unattended security updates are working on the server, and how to
get failure/report emails delivered via Mailgun.

Server: `turnushjelper-2` (Hetzner, Ubuntu). Outbound port 25 is **blocked by
Hetzner** — mail must relay through Mailgun on port 587.

---

## 1. Verify automatic security updates are working

Auto security updates are handled by the `unattended-upgrades` package. Run these
**on the server** (via SSH).

### Is it installed and scheduled?

```bash
dpkg -l unattended-upgrades
systemctl status unattended-upgrades
systemctl status apt-daily.timer apt-daily-upgrade.timer
```

The timers should be `enabled` and `active (waiting)`.

### Is it actually enabled? (master switches)

```bash
cat /etc/apt/apt.conf.d/20auto-upgrades
```

Both must be `"1"`:

```
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
```

### Which origins does it install from?

```bash
grep -A15 'Allowed-Origins\|Origins-Pattern' /etc/apt/apt.conf.d/50unattended-upgrades
```

The `-security` line must be **uncommented** (no leading `//`). `-updates`,
`-proposed`, `-backports` are commented out by default — that's correct; only
security fixes auto-install.

### Proof it has actually run (the real test)

```bash
sudo tail -n 50 /var/log/unattended-upgrades/unattended-upgrades.log
zless /var/log/unattended-upgrades/unattended-upgrades-dpkg.log*
```

Look for daily `Starting unattended upgrades script` entries and
`Packages that will be upgraded: ...` / `All upgrades installed` lines.

### Dry run — what would it do right now?

```bash
sudo unattended-upgrade --dry-run --debug
```

Confirms candidates come from `*-security` and that `*-updates` is pinned out
(`-32768`). Lists pending security upgrades without installing them.

---

## 2. Mail notifications

By default unattended-upgrades logs:

```
ERROR No /usr/bin/mail or /usr/sbin/sendmail, can not send mail.
```

This only means no notification email is sent — upgrades still work. To fix it
you need (a) a `mail` binary and (b) a working mail transport.

### Install the mail client

```bash
sudo apt install bsd-mailx
which mail   # -> /usr/bin/mail
```

### Set the recipient

Edit `/etc/apt/apt.conf.d/50unattended-upgrades`:

```
Unattended-Upgrade::Mail "solveottooren@gmail.com";
# optional: mail on every change, not just errors
Unattended-Upgrade::MailReport "on-change";
```

### Why direct delivery does NOT work

Hetzner blocks outbound port 25. A direct send to Gmail fails with:

```
connect to gmail-smtp-in.l.google.com[...]:25: Connection timed out
```

**Do not open port 25.** Even if unblocked, mail from a fresh cloud IP with no
SPF/DKIM/PTR gets rejected or spam-foldered. Relay through Mailgun on port 587
instead (Mailgun already has domain reputation + SPF/DKIM for the app).

---

## 3. Relay outbound mail through Mailgun (port 587)

You need Mailgun **SMTP credentials** (Mailgun dashboard → Sending → Domain →
SMTP). These are the SMTP username/password, *not* the API key used by the app.
Username looks like `postmaster@mg.yourdomain.com`.

### 1. Point Postfix at Mailgun

Add to the bottom of `/etc/postfix/main.cf`:

```
relayhost = [smtp.mailgun.org]:587
smtp_sasl_auth_enable = yes
smtp_sasl_password_maps = hash:/etc/postfix/sasl_passwd
smtp_sasl_security_options = noanonymous
smtp_tls_security_level = encrypt
smtp_use_tls = yes
```

### 2. Store the credentials

```bash
sudo tee /etc/postfix/sasl_passwd > /dev/null <<'EOF'
[smtp.mailgun.org]:587 postmaster@mg.yourdomain.com:YOUR_MAILGUN_SMTP_PASSWORD
EOF
sudo chmod 600 /etc/postfix/sasl_passwd
sudo postmap /etc/postfix/sasl_passwd
```

### 3. Reload and flush the queue

```bash
sudo systemctl reload postfix
sudo postqueue -f
```

### 4. Test end-to-end

```bash
echo "test from turnushjelper server" | mail -s "mailx test" solveottooren@gmail.com
sudo tail -n 20 /var/log/mail.log
mailq
```

Success = `status=sent (250 ... queued as ...)` in the log and an **empty**
`mailq`. Check Gmail inbox + spam folder on the first send.

> Mailgun sandbox domains only send to *authorized recipients*. If using the
> sandbox domain (not a verified `mg.` domain), add the recipient in Mailgun first.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `connect to ...:25: Connection timed out` | Hetzner blocks port 25 | Use Mailgun relay (section 3) |
| `mailq` shows queued message with `*` | Message stuck / not delivered | Check `sudo tail /var/log/mail.log` for reason |
| `535 Authentication failed` in mail.log | Wrong Mailgun SMTP creds | Re-check user/pass, re-run `postmap` |
| `warning: not owned by root: /var/spool/postfix/etc/resolv.conf` | Harmless | `sudo chown root:root /var/spool/postfix/etc/resolv.conf` |
| Log commands print nothing | Need root to read mail log/journal | Prefix with `sudo` |
