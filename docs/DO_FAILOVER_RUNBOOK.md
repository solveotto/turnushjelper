# DO Failover Runbook

PythonAnywhere is the primary server. This Droplet is a warm standby — it receives a daily MySQL backup from PA and restores it automatically at 2:30 AM UTC.

## Before Failing Over

1. Check that today's restore ran successfully:
   ```
   tail -20 app/logs/do_restore.log
   ```
   Look for `Restore complete`. If missing, the last successful restore timestamp tells you the data lag.

2. Confirm the DO app is running:
   ```
   systemctl status turnushjelper
   ```

## Failover Steps (Cloudflare DNS)

1. Log in to the Cloudflare dashboard
2. Go to **DNS** for your domain
3. Find the **A record** pointing to the PythonAnywhere IP
4. Click **Edit** — replace the IP with the DO Droplet's public IP
5. Leave proxy status as **Proxied** (orange cloud)
6. Click **Save**

Propagation is near-instant with Cloudflare proxying (seconds, not minutes).

7. Verify in a browser that the site loads and you can log in

## Data Lag

The DO database contains data up to the last successful restore (2:30 AM UTC). Any writes (favorites, user changes) made after that time on PA are not present on DO.

## Failing Back to PA

Once PA is healthy:

1. If significant writes happened on DO during the outage, dump DO's database and import it to PA:
   ```bash
   # On DO
   mysqldump -h127.0.0.1 -uUSER -pPASS DATABASE > /tmp/do_export.sql
   # Transfer to PA, then on PA:
   mysql -h HOST -u USER -p DATABASE < do_export.sql
   ```

2. In Cloudflare DNS, change the A record back to the PA IP

3. Verify PA is serving traffic

## DO Droplet Setup (one-time)

If setting up from scratch:

```bash
# As root on Ubuntu 24.04
apt update && apt install -y python3.12 python3.12-venv mysql-server nginx

# Create deploy user
adduser deploy
su - deploy

# Clone repo and set up venv
git clone <repo-url> turnushjelper
cd turnushjelper
python3.12 -m venv venv
venv/bin/pip install -r requirements.txt

# Configure .env
cp .env.example .env
# Edit .env: set DB_TYPE=mysql, MYSQL_HOST=127.0.0.1, and all secrets

# Create MySQL DB and user matching .env, then run migrations
venv/bin/python -m alembic upgrade head

# Create backup directory (must match DO_BACKUP_PATH in PA .env)
mkdir -p /home/deploy/backups

# Add cron job for nightly restore
crontab -e
# Add: 30 2 * * * /home/deploy/turnushjelper/venv/bin/python /home/deploy/turnushjelper/app/scripts/backup/do_restore.py
```

## SSH Key Setup (PA → DO)

On PythonAnywhere:
```bash
ssh-keygen -t ed25519 -f ~/.ssh/do_backup_key -N ""
cat ~/.ssh/do_backup_key.pub
```

On DO Droplet (as deploy user):
```bash
echo "PASTE_PUBLIC_KEY_HERE" >> ~/.ssh/authorized_keys
```

Then add to PA `.env`:
```
DO_BACKUP_HOST=<droplet-public-ip>
DO_BACKUP_USER=deploy
DO_BACKUP_PATH=/home/deploy/backups
DO_BACKUP_SSH_KEY=/home/solveottooren/.ssh/do_backup_key
DO_BACKUP_PORT=22
```

## Testing

Manual test on PA (verify backup pushes to DO):
```bash
python app/scripts/backup/offsite_backup.py
# Check offsite_backup.log for "DO destination: ok"
```

Manual test on DO (verify restore works):
```bash
python app/scripts/backup/do_restore.py
# Check do_restore.log for "Restore complete"
```
