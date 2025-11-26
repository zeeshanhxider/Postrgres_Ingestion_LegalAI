# Connecting to PostgreSQL via pgAdmin

## Connection Details

| Setting      | Value                                 |
| ------------ | ------------------------------------- |
| **Host**     | `localhost` or `host.docker.internal` |
| **Port**     | `5433`                                |
| **Database** | `cases_llama3_3`                      |
| **Username** | `postgres`                            |
| **Password** | `postgres123`                         |

## Steps

1. Open pgAdmin → Right-click **Servers** → **Register** → **Server**

2. **General tab:**

   - Name: `Legal AI Database`

3. **Connection tab:**

   - Host: `localhost` (from Windows) or `host.docker.internal` (from another container)
   - Port: `5433`
   - Maintenance database: `cases_llama3_3`
   - Username: `postgres`
   - Password: `postgres123`
   - ☑️ Save password

4. Click **Save**

## Host Options

| Your pgAdmin Setup                     | Use Host               |
| -------------------------------------- | ---------------------- |
| Installed on Windows                   | `localhost`            |
| Running in a separate Docker container | `host.docker.internal` |
| Added to same `docker-compose.yml`     | `legal_ai_postgres`    |
