# Secure Deployment Guide - Patched Chess Ultimate App

**Critical Security Fixes Applied:** CVE-2025-55182, CVE-2025-55183, CVE-2025-55184, CVE-2025-67779

---

## Pre-Deployment Checklist

### ✅ Completed Steps
- [x] Updated Next.js to 16.1.1+ (patched)
- [x] Updated React to 19.2.3+ (patched)
- [x] Updated React-DOM to 19.2.3+ (patched)
- [x] Verified no critical CVEs in npm audit
- [x] Backed up environment variables from old droplet
- [x] Backed up nginx configuration
- [x] Committed security patches to git

### Backed Up Files
- Environment variables: `/tmp/droplet-env-backup.txt`
- Nginx config: `/tmp/nginx-backup.conf`

---

## Step 1: Destroy Compromised Droplet

**CRITICAL:** The old droplet (159.223.42.132) is compromised with cryptocurrency mining malware. It MUST be destroyed.

```bash
# Stop all containers (already done)
# ssh root@159.223.42.132 "cd /root/chess-app && docker-compose down"

# Option 1: Via DigitalOcean CLI
doctl compute droplet delete <droplet-id> --force

# Option 2: Via DigitalOcean Dashboard
# 1. Log in to https://cloud.digitalocean.com
# 2. Navigate to Droplets
# 3. Select droplet with IP 159.223.42.132
# 4. Click "Destroy" → Confirm
```

---

## Step 2: Create New Clean Droplet

### Recommended Specifications
- **OS:** Ubuntu 24.04 LTS x64
- **Size:** Basic - $12/month (2 GB RAM, 1 vCPU, 50 GB SSD)
- **Region:** Same as before (for DNS consistency)
- **Hostname:** chess-empire-prod
- **Tags:** production, patched, secure

### Via DigitalOcean CLI
```bash
doctl compute droplet create chess-empire-prod \
  --image ubuntu-24-04-x64 \
  --size s-2vcpu-2gb \
  --region nyc1 \
  --ssh-keys <your-ssh-key-id> \
  --enable-monitoring \
  --tag-names production,patched
```

### Via Dashboard
1. Click "Create" → "Droplets"
2. Choose Ubuntu 24.04 LTS
3. Select Basic plan - $12/month (2GB RAM)
4. Add your SSH key
5. Enable monitoring
6. Create droplet

**Save the new IP address!** You'll need it for deployment.

---

## Step 3: Initial Server Setup

```bash
# SSH into new droplet
ssh root@<NEW_IP>

# Update system
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
systemctl enable docker
systemctl start docker

# Install Docker Compose
apt install docker-compose-plugin -y

# Configure UFW firewall (CRITICAL for security)
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# Verify firewall
ufw status verbose
```

---

## Step 4: Deploy Patched Application

### On Local Machine

```bash
# Navigate to project directory
cd /home/marblemaster/Desktop/Cursor/chess-ultimate-app-local

# Verify patched versions
cd frontend && npm list next react react-dom --depth=0
# Should show: next@16.1.1+, react@19.2.3+, react-dom@19.2.3+

# Create deployment tarball (excludes node_modules)
cd /home/marblemaster/Desktop/Cursor
tar --exclude='chess-ultimate-app-local/frontend/node_modules' \
    --exclude='chess-ultimate-app-local/frontend/.next' \
    --exclude='chess-ultimate-app-local/backend/__pycache__' \
    --exclude='chess-ultimate-app-local/.git' \
    -czf chess-app-patched.tar.gz chess-ultimate-app-local/

# Transfer to new droplet
scp chess-app-patched.tar.gz root@<NEW_IP>:/root/

# Transfer environment variables (EDIT FIRST - update CORS_ALLOWED_ORIGINS)
# Edit /tmp/droplet-env-backup.txt to replace old IP with new IP
sed "s/159.223.42.132/<NEW_IP>/g" /tmp/droplet-env-backup.txt > /tmp/env-production-new.txt
scp /tmp/env-production-new.txt root@<NEW_IP>:/root/
```

### On New Droplet

```bash
# Extract application
cd /root
tar -xzf chess-app-patched.tar.gz
mv chess-ultimate-app-local chess-app
cd chess-app

# Move environment file
mv /root/env-production-new.txt .env.production

# CRITICAL: Set correct permissions
chmod 600 .env.production

# Build and start containers
docker-compose -f docker-compose.prod.yml up -d --build

# Monitor build progress
docker-compose -f docker-compose.prod.yml logs -f
```

---

## Step 5: Configure Nginx

```bash
# Install nginx
apt install nginx -y

# Create nginx config
cat > /etc/nginx/sites-available/default << 'EOF'
server {
    listen 80;
    server_name <NEW_IP>;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:5001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /health {
        proxy_pass http://127.0.0.1:5001/health;
        access_log off;
    }
}
EOF

# Test nginx config
nginx -t

# Restart nginx
systemctl restart nginx
systemctl enable nginx
```

---

## Step 6: Security Verification

### Verify Patched Versions
```bash
# Check running containers
docker ps

# Verify Next.js version in frontend container
docker exec chess-ultimate-frontend npm list next react react-dom --depth=0

# Should output:
# ├── next@16.1.1 or higher
# ├── react@19.2.3 or higher
# └── react-dom@19.2.3 or higher
```

### Verify No Malware
```bash
# Check for suspicious processes
ps aux | grep -E 'hBEs0oh|LLm09W8K|tsRb1y|7Y1ulx|SasA0|l3H171|kokz'
# Should return: (no output)

# Check network connections
ss -tlnp
# Should ONLY show: ports 22, 80, 443 (and internal Docker ports)

# Verify no database ports exposed
ss -tlnp | grep -E ':6379|:6380|:8080|:8081|:50052'
# Should return: (no output)

# Check Docker resource usage (should be normal)
docker stats --no-stream

# Monitor logs for errors
docker-compose -f docker-compose.prod.yml logs --tail=100
```

### Test Application
```bash
# Test frontend
curl -I http://<NEW_IP>
# Should return: HTTP/1.1 200 OK

# Test backend API
curl http://<NEW_IP>/api/health
# Should return: JSON with status

# Test from browser
# Navigate to: http://<NEW_IP>
# Application should load without errors
```

---

## Step 7: Post-Deployment Monitoring

### Monitor for 24-48 Hours

```bash
# Watch container logs
docker-compose -f docker-compose.prod.yml logs -f

# Monitor system resources
htop
# or
docker stats

# Check for OOM kills (malware signature)
journalctl --since "1 hour ago" | grep -i oom

# Monitor network traffic
ss -s
```

### Set Up Alerts (Optional)
```bash
# Install fail2ban for SSH brute force protection
apt install fail2ban -y
systemctl enable fail2ban
systemctl start fail2ban
```

---

## Step 8: Update DNS (If Using Domain)

If you're using a domain name:
1. Update A record to point to new droplet IP
2. Wait for DNS propagation (5-60 minutes)
3. Test with: `dig yourdomain.com`

---

## Step 9: Destroy Old Droplet (Final)

**ONLY after verifying new deployment works:**

```bash
# Via DigitalOcean Dashboard
# 1. Confirm new droplet is working
# 2. Destroy old droplet (159.223.42.132)
# 3. Delete any snapshots/backups of compromised droplet
```

---

## Security Best Practices Going Forward

### 1. Keep Dependencies Updated
```bash
# Check for updates weekly
npm outdated

# Update to latest patch versions
npm update

# Run security audit
npm audit
```

### 2. Monitor Security Advisories
- Subscribe to Next.js security updates: https://nextjs.org/blog
- Subscribe to React security updates: https://react.dev/blog
- Check GitHub Security Advisories for dependencies

### 3. Regular Security Scans
```bash
# Monthly security audit
npm audit

# Check for exposed ports
ss -tlnp

# Verify firewall status
ufw status verbose

# Check for suspicious processes
ps aux | head -50
```

### 4. Container Security
```bash
# Run containers as non-root (already configured)
# Limit container resources (already configured)
# Never expose database ports externally (already configured)

# Regularly update base images
docker pull node:20-alpine
docker pull python:3.11-slim

# Rebuild containers with updated images quarterly
docker-compose -f docker-compose.prod.yml build --no-cache
```

---

## Troubleshooting

### Issue: Containers won't start
```bash
# Check logs
docker-compose -f docker-compose.prod.yml logs

# Check disk space
df -h

# Restart Docker
systemctl restart docker
```

### Issue: Can't access application
```bash
# Check nginx status
systemctl status nginx

# Check nginx logs
tail -f /var/log/nginx/error.log

# Verify containers are running
docker ps
```

### Issue: High memory usage
```bash
# Check container stats
docker stats

# Verify resource limits are enforced
docker inspect chess-ultimate-frontend | grep -A 10 Memory
```

---

## Support

If you encounter issues:
1. Check logs: `docker-compose logs`
2. Verify firewall: `ufw status`
3. Check disk space: `df -h`
4. Review security summary: [SECURITY_PATCH_SUMMARY.md](SECURITY_PATCH_SUMMARY.md)

---

**Last Updated:** 2026-01-10
**Patched Versions:** Next.js 16.1.1, React 19.2.3
**Security Status:** ✅ All Critical CVEs Patched
