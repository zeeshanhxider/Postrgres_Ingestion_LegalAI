# Windows Setup Guide: WSL + PostgreSQL 16 + pgvector

Complete step-by-step guide to set up WSL (Windows Subsystem for Linux), PostgreSQL 16, and pgvector extension on Windows.

---

## Overview

This guide will help you:

1. Install WSL2 (Windows Subsystem for Linux)
2. Install Ubuntu 22.04 on WSL
3. Install PostgreSQL 16
4. Install pgvector extension
5. Configure PostgreSQL for remote access from Windows
6. Set up the cases_llama3.3 database

**Estimated time:** 30-45 minutes

---

## Part 1: Install WSL2

### Step 1: Enable WSL

Open **PowerShell as Administrator** and run:

```powershell
# Enable WSL and Virtual Machine Platform
wsl --install
```

This single command will:

- Enable WSL feature
- Enable Virtual Machine Platform
- Install Ubuntu (default distribution)
- Set WSL 2 as default

**You will need to restart your computer after this step.**

### Step 2: Restart Computer

```powershell
Restart-Computer
```

### Step 3: Verify WSL Installation

After restart, open PowerShell and check:

```powershell
wsl --version
```

You should see output like:

```
WSL version: 2.0.x.x
Kernel version: 5.15.x.x
```

### Step 4: Check Installed Distributions

```powershell
wsl --list --verbose
```

Expected output:

```
  NAME      STATE           VERSION
* Ubuntu    Running         2
```

---

## Part 2: Set Up Ubuntu on WSL

### Step 1: Launch Ubuntu

Click **Start Menu** → Type **"Ubuntu"** → Click **Ubuntu** app

**First time only:** You'll be asked to create a username and password.

```bash
# Example:
Enter new UNIX username: yourname
New password: ********
Retype new password: ********
```

**IMPORTANT:** Remember this password - you'll need it for `sudo` commands.

### Step 2: Update Ubuntu

```bash
sudo apt update
sudo apt upgrade -y
```

This may take 5-10 minutes.

---

## Part 3: Install PostgreSQL 16

### Step 1: Add PostgreSQL Repository

```bash
# Create the file repository configuration
sudo sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'

# Import the repository signing key
wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -

# Update package lists
sudo apt update
```

### Step 2: Install PostgreSQL 16

```bash
sudo apt install -y postgresql-16 postgresql-contrib-16
```

### Step 3: Verify Installation

```bash
psql --version
```

Expected output:

```
psql (PostgreSQL) 16.x
```

### Step 4: Check PostgreSQL Status

```bash
sudo service postgresql status
```

Should show: `online`

If not running, start it:

```bash
sudo service postgresql start
```

---

## Part 4: Install pgvector Extension

### Step 1: Install Build Tools

```bash
sudo apt install -y build-essential git postgresql-server-dev-16
```

### Step 2: Clone pgvector Repository

```bash
cd ~
git clone --branch v0.7.4 https://github.com/pgvector/pgvector.git
cd pgvector
```

### Step 3: Build and Install pgvector

```bash
make
sudo make install
```

### Step 4: Verify Installation

```bash
ls /usr/lib/postgresql/16/lib/ | grep vector
```

Expected output:

```
vector.so
```

---

## Part 5: Configure PostgreSQL

### Step 1: Switch to PostgreSQL User

```bash
sudo -i -u postgres
```

Your prompt should change to: `postgres@COMPUTERNAME:~$`

### Step 2: Set PostgreSQL Password

```bash
psql -c "ALTER USER postgres WITH PASSWORD 'your_password_here';"
```

Replace `your_password_here` with a strong password (e.g., `postgres123`).

### Step 3: Exit PostgreSQL User

```bash
exit
```

### Step 4: Configure Remote Access

Edit PostgreSQL configuration to allow connections from Windows:

```bash
sudo nano /etc/postgresql/16/main/postgresql.conf
```

Find this line (around line 59):

```
#listen_addresses = 'localhost'
```

Change it to:

```
listen_addresses = '*'
```

**To save in nano:**

- Press `Ctrl + O` (WriteOut)
- Press `Enter`
- Press `Ctrl + X` (Exit)

### Step 5: Configure Authentication

```bash
sudo nano /etc/postgresql/16/main/pg_hba.conf
```

Add this line at the end of the file:

```
host    all             all             0.0.0.0/0               md5
```

**Save and exit** (Ctrl+O, Enter, Ctrl+X)

### Step 6: Restart PostgreSQL

```bash
sudo service postgresql restart
```

### Step 7: Verify PostgreSQL is Running

```bash
sudo service postgresql status
```

Should show: `online`

---

## Part 6: Create Database and Enable pgvector

### Step 1: Connect to PostgreSQL

```bash
sudo -u postgres psql
```

You should see the PostgreSQL prompt: `postgres=#`

### Step 2: Create Database

```sql
CREATE DATABASE cases_llama3_3;
```

Note: We use `cases_llama3_3` instead of `cases_llama3.3` because dots in database names can cause issues.

### Step 3: Connect to Database

```sql
\c cases_llama3_3
```

### Step 4: Enable pgvector Extension

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### Step 5: Verify pgvector

```sql
SELECT * FROM pg_extension WHERE extname = 'vector';
```

Expected output:

```
 oid  | extname | extowner | extnamespace | extrelocatable | extversion | ...
------+---------+----------+--------------+----------------+------------+
 xxxxx| vector  |       10 |         2200 | f              | 0.7.4      |
```

### Step 6: Test pgvector

```sql
CREATE TABLE test_vector (
    id SERIAL PRIMARY KEY,
    embedding VECTOR(1024)
);

-- Insert test data
INSERT INTO test_vector (embedding) VALUES ('[1,2,3]');

-- Query test data
SELECT * FROM test_vector;

-- Clean up
DROP TABLE test_vector;
```

### Step 7: Exit PostgreSQL

```sql
\q
```

---

## Part 7: Get WSL IP Address

### Step 1: Find WSL IP Address

```bash
hostname -I
```

Example output: `172.23.144.1`

**Copy this IP address** - you'll need it to connect from Windows.

### Step 2: Test Connection from WSL

```bash
psql -h localhost -U postgres -d cases_llama3_3
```

Enter your password when prompted. If successful, you'll see the PostgreSQL prompt.

Exit with `\q`

---

## Part 8: Connect from Windows

### Step 1: Install psql on Windows (Optional but Recommended)

Download PostgreSQL for Windows (just the client tools):

- Go to: https://www.postgresql.org/download/windows/
- Download PostgreSQL 16 installer
- During installation, **uncheck** "PostgreSQL Server" (we only need client tools)
- Install only: **Command Line Tools** and **pgAdmin 4**

### Step 2: Test Connection from Windows PowerShell

Open **PowerShell** (not as admin) and run:

```powershell
# Replace 172.23.144.1 with YOUR WSL IP address
psql -h 172.23.144.1 -U postgres -d cases_llama3_3
```

Enter your password when prompted.

If successful, you'll see:

```
cases_llama3_3=#
```

Exit with `\q`

### Step 3: Update Environment Variables

In PowerShell, set your database connection:

```powershell
$env:DATABASE_URL = "postgresql://postgres:your_password@172.23.144.1:5432/cases_llama3_3"
```

**To make it permanent:**

1. Press `Windows + R`
2. Type `sysdm.cpl` and press Enter
3. Click **Advanced** tab
4. Click **Environment Variables**
5. Under **User variables**, click **New**
6. Variable name: `DATABASE_URL`
7. Variable value: `postgresql://postgres:your_password@172.23.144.1:5432/cases_llama3_3`
8. Click **OK**

---

## Part 9: Run Brief Migration

### Step 1: Navigate to Project

```powershell
cd d:\freelance\Dobbs_Data\Postgres_Ingestion_LegalAI
```

### Step 2: Test Connection

```powershell
# Test psql connection
psql -h 172.23.144.1 -U postgres -d cases_llama3_3 -c "SELECT version();"
```

### Step 3: Run Migration

**Option A: Using PowerShell Script**

Edit `scripts/run_brief_migration.ps1` to update database host:

```powershell
# Change this line in the script:
$DB_HOST = if ($env:DB_HOST) { $env:DB_HOST } else { "172.23.144.1" }
```

Then run:

```powershell
.\scripts\run_brief_migration.ps1
```

**Option B: Manual Migration**

```powershell
# Set environment variable for this session
$env:PGPASSWORD = "your_password"

# Run migration
psql -h 172.23.144.1 -U postgres -d cases_llama3_3 -f scripts/migrate_briefs_schema.sql
```

### Step 4: Verify Migration

```powershell
psql -h 172.23.144.1 -U postgres -d cases_llama3_3 -c "SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'brief%' ORDER BY table_name;"
```

Expected output:

```
      table_name
-----------------------
 brief_arguments
 brief_chunks
 brief_citations
 brief_phrases
 brief_sentences
 brief_word_occurrence
 briefs
(7 rows)
```

---

## Part 10: Start Ingesting Briefs

### Step 1: Update Python Connection String

In your project, update database connection to use WSL IP:

```python
# In app/database.py or wherever connection is defined
DATABASE_URL = "postgresql://postgres:your_password@172.23.144.1:5432/cases_llama3_3"
```

### Step 2: Run Batch Processor

```powershell
python batch_process_briefs.py --briefs-dir downloaded-briefs --case-folder 83895-4
```

---

## Troubleshooting

### Issue: "wsl: command not found" in PowerShell

**Solution:** WSL is not installed. Make sure you:

1. Ran `wsl --install` as Administrator
2. Restarted your computer
3. Your Windows version is Windows 10 version 2004+ or Windows 11

Check Windows version:

```powershell
winver
```

### Issue: Ubuntu doesn't start

**Solution:**

```powershell
# Reset WSL
wsl --shutdown
wsl
```

### Issue: "could not connect to server"

**Possible causes and solutions:**

1. **PostgreSQL not running in WSL**

   ```bash
   # In WSL Ubuntu terminal
   sudo service postgresql status
   sudo service postgresql start
   ```

2. **Wrong IP address**

   ```bash
   # Get correct IP in WSL
   hostname -I
   ```

3. **Firewall blocking connection**
   - Open Windows Defender Firewall
   - Allow PostgreSQL port 5432
   - Or temporarily disable firewall to test

### Issue: "password authentication failed"

**Solution:**

```bash
# In WSL, reset password
sudo -u postgres psql -c "ALTER USER postgres WITH PASSWORD 'newpassword';"
```

### Issue: pgvector installation fails

**Solution:**

```bash
# Make sure you have all dependencies
sudo apt install -y build-essential git postgresql-server-dev-16

# Try building again
cd ~/pgvector
make clean
make
sudo make install

# Restart PostgreSQL
sudo service postgresql restart
```

### Issue: WSL IP address changes after restart

**This is normal.** WSL gets a new IP on each boot.

**Solutions:**

**Option 1: Use localhost with port forwarding**

```powershell
# Forward port 5432 from WSL to Windows
wsl -d Ubuntu -u root -- sh -c "sysctl -w net.ipv4.conf.all.forwarding=1"
netsh interface portproxy add v4tov4 listenport=5432 listenaddress=0.0.0.0 connectport=5432 connectaddress=$(wsl hostname -I)
```

Then use `localhost` instead of WSL IP:

```
postgresql://postgres:password@localhost:5432/cases_llama3_3
```

**Option 2: Create a script to get WSL IP**

```powershell
# Save as get_wsl_ip.ps1
$wslIp = wsl hostname -I
$wslIp = $wslIp.Trim()
Write-Host "WSL IP: $wslIp"
$env:DATABASE_URL = "postgresql://postgres:password@${wslIp}:5432/cases_llama3_3"
Write-Host "DATABASE_URL updated"
```

Run before each session:

```powershell
.\get_wsl_ip.ps1
```

### Issue: PostgreSQL doesn't start automatically

**Solution:** Create a startup script

```bash
# In WSL, create startup script
sudo nano /etc/init.d/postgresql-start

# Add this content:
#!/bin/bash
service postgresql start

# Make it executable
sudo chmod +x /etc/init.d/postgresql-start
```

**Or start manually each time:**

```bash
sudo service postgresql start
```

---

## Auto-Start PostgreSQL (Optional)

### Option 1: WSL Task Scheduler

Create a Windows Task that starts PostgreSQL when you log in:

1. Open **Task Scheduler**
2. Create Basic Task
3. Name: "Start PostgreSQL in WSL"
4. Trigger: At log on
5. Action: Start a program
6. Program: `wsl`
7. Arguments: `-d Ubuntu -u root service postgresql start`

### Option 2: .bashrc Auto-start

```bash
# Add to ~/.bashrc in WSL
echo 'sudo service postgresql start' >> ~/.bashrc
```

---

## Quick Reference

### Start/Stop PostgreSQL

```bash
# In WSL Ubuntu
sudo service postgresql start
sudo service postgresql stop
sudo service postgresql restart
sudo service postgresql status
```

### Connect to Database

```bash
# From WSL
psql -U postgres -d cases_llama3_3

# From Windows PowerShell (replace IP)
psql -h 172.23.144.1 -U postgres -d cases_llama3_3
```

### Get WSL IP

```bash
# In WSL
hostname -I
```

### Check pgvector

```sql
-- In psql
\c cases_llama3_3
SELECT * FROM pg_extension WHERE extname = 'vector';
```

### Database URL Format

```
postgresql://postgres:password@WSL_IP:5432/cases_llama3_3
```

Example:

```
postgresql://postgres:postgres123@172.23.144.1:5432/cases_llama3_3
```

---

## Next Steps

After completing this setup:

1. ✅ WSL2 installed and running
2. ✅ Ubuntu 22.04 installed
3. ✅ PostgreSQL 16 installed and running
4. ✅ pgvector extension installed
5. ✅ cases_llama3_3 database created
6. ✅ Can connect from Windows

**Now proceed to:**

- Run brief migration: `.\scripts\run_brief_migration.ps1`
- Test single brief: `python batch_process_briefs.py --case-folder 83895-4`
- Process all briefs: `python batch_process_briefs.py --briefs-dir downloaded-briefs`

See `TODO_BRIEF_MIGRATION.md` for full checklist.

---

## Additional Resources

- **WSL Documentation:** https://docs.microsoft.com/en-us/windows/wsl/
- **PostgreSQL Documentation:** https://www.postgresql.org/docs/16/
- **pgvector GitHub:** https://github.com/pgvector/pgvector
- **Ubuntu on WSL:** https://ubuntu.com/wsl

---

## Summary

You now have:

- A full Linux environment (Ubuntu) running on Windows
- PostgreSQL 16 with pgvector extension
- Ability to run PostgreSQL commands from both WSL and Windows
- Ready to migrate briefs schema and ingest briefs

**Total setup time:** 30-45 minutes
**Disk space used:** ~2-3GB for Ubuntu + PostgreSQL
