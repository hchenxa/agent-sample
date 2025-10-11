# Troubleshooting Guide - Jenkins Analytics Features

## Issue: Jenkins Analytics Commands Not Working

### Symptoms:
- Commands like `/jenkins server info`, `/jenkins job analytics`, etc. don't work
- No error message or response from the chatbot
- Jenkins commands seem to be ignored

### Root Cause:
The Jenkins client may not be properly initialized when you try to use the analytics commands.

### Solution Steps:

#### Step 1: Check Jenkins Configuration in Sidebar

1. Look for the **"Jenkins Configuration"** section in the left sidebar
2. Make sure it's **expanded** (click on it if collapsed)
3. Verify all three fields are filled in:
   - **Jenkins URL** (e.g., `http://your-jenkins-server:8080`)
   - **Jenkins Username** (your Jenkins username)
   - **Jenkins API Token** (your Jenkins API token, not password!)

#### Step 2: Verify Initialization

After entering your Jenkins credentials, you should see:
- ✅ Green success message: **"Jenkins client initialized successfully!"**

If you see an error instead:
- ❌ Red error message: Check your credentials and Jenkins URL
- Make sure Jenkins is accessible from your network
- Verify the API token is correct (generate a new one if needed)

#### Step 3: Check Debug Console

Open your terminal/console where you're running Streamlit and look for these debug messages:

**When Jenkins is properly configured:**
```
DEBUG: Jenkins client initialized. URL: http://jenkins:8080, User: your-username
DEBUG [main.py]: After setup_configurations - jenkins_client: True
```

**When Jenkins is NOT configured:**
```
DEBUG: Jenkins not configured. URL: True, User: True, Token: False
DEBUG [main.py]: After setup_configurations - jenkins_client: False
```

#### Step 4: Test with a Simple Command

Try the simplest Jenkins command first:
```
/jenkins server info
```

You should see debug output like:
```
DEBUG: Matched server info command. jenkins_client exists: True
```

If you see `jenkins_client exists: False`, the client is not initialized.

---

## How to Get Jenkins API Token

If you don't have a Jenkins API token:

1. Log into your Jenkins server
2. Click your username in the top-right corner
3. Click **"Configure"**
4. Scroll down to **"API Token"** section
5. Click **"Add new Token"**
6. Give it a name (e.g., "Chatbot Access")
7. Click **"Generate"**
8. **Copy the token immediately** (you won't be able to see it again!)
9. Paste it into the **"Jenkins API Token"** field in the sidebar

---

## Common Issues

### Issue: "Failed to initialize Jenkins client: Connection Error"

**Cause:** Cannot connect to Jenkins server

**Solutions:**
- Verify Jenkins URL is correct and accessible
- Check if Jenkins requires VPN connection
- Test the URL in your browser
- Make sure port number is included (e.g., `:8080`)
- Check firewall settings

### Issue: "Failed to initialize Jenkins client: Authentication Error"

**Cause:** Invalid credentials

**Solutions:**
- Verify username is correct (case-sensitive)
- Generate a new API token
- Make sure you're using an **API token**, not a password
- Check if your Jenkins account is active

### Issue: Commands work but return "Error fetching..."

**Cause:** Client is initialized but API calls are failing

**Solutions:**
- Check if your Jenkins user has permissions to view jobs
- Verify you have read access to all jobs
- Check if Jenkins is using a self-signed SSL certificate (disable SSL verification if needed)

### Issue: Analytics commands timeout or take too long

**Cause:** Large Jenkins instance with many jobs

**Solutions:**
- Be patient - analyzing 100+ jobs can take 10-30 seconds
- Jenkins server might be slow or under load
- Consider reducing the number of jobs in your Jenkins instance

---

## Using Environment Variables (Alternative)

Instead of entering credentials in the sidebar every time, you can set environment variables:

```bash
export JENKINS_URL="http://your-jenkins-server:8080"
export JENKINS_USERNAME="your-username"
export JENKINS_API_TOKEN="your-api-token"
```

Then run Streamlit:
```bash
streamlit run main.py
```

The credentials will be auto-filled from environment variables.

---

## Debug Mode

To enable more verbose debugging:

1. Run Streamlit with:
```bash
streamlit run main.py --logger.level=debug
```

2. Watch the console output for detailed error messages

---

## Testing Jenkins Connection

You can test your Jenkins connection independently using this Python script:

```python
import jenkins

server = jenkins.Jenkins(
    'http://your-jenkins-server:8080',
    username='your-username',
    password='your-api-token'
)

# Test connection
try:
    version = server.get_version()
    print(f"Successfully connected! Jenkins version: {version}")

    # List jobs
    jobs = server.get_jobs()
    print(f"Found {len(jobs)} jobs")
except Exception as e:
    print(f"Connection failed: {e}")
```

If this script works, the issue is with the chatbot configuration. If it fails, the issue is with your Jenkins credentials or network.

---

## Still Having Issues?

If none of the above solutions work:

1. **Check the logs**: Look at the terminal output for detailed error messages
2. **Try other Jenkins commands**: Test with `/jenkins list jobs` to see if basic commands work
3. **Restart Streamlit**: Sometimes a fresh restart helps
4. **Check Jenkins server**: Make sure Jenkins itself is running and accessible
5. **Report an issue**: Create a GitHub issue with:
   - Error messages from console
   - Jenkins version
   - Command you tried to run
   - Whether basic Jenkins commands work

---

## Quick Diagnostic Checklist

- [ ] Jenkins URL is accessible in browser
- [ ] Jenkins username is correct
- [ ] Using API token (not password)
- [ ] All three fields filled in sidebar
- [ ] Green success message appears
- [ ] Debug shows `jenkins_client: True`
- [ ] Can run `/jenkins list jobs` successfully
- [ ] Jenkins user has permissions to view jobs

If all items are checked, analytics commands should work!

---

**Last Updated:** 2025-10-11
