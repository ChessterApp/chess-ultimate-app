#!/bin/bash
# Auto-setup SSL for chesster.io once DNS propagates
# Run via: setsid nohup bash /root/chess-app/setup-ssl.sh > /tmp/ssl-setup.log 2>&1 &

MAX_ATTEMPTS=60  # 60 attempts x 60 seconds = 1 hour max wait
ATTEMPT=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    ATTEMPT=$((ATTEMPT + 1))
    RESULT=$(dig @8.8.8.8 +short chesster.io A 2>/dev/null)
    
    if [ "$RESULT" = "104.248.190.155" ]; then
        echo "$(date): DNS propagated! chesster.io -> $RESULT"
        echo "$(date): Running certbot..."
        
        certbot --nginx -d chesster.io -d www.chesster.io \
            --non-interactive --agree-tos \
            --email admin@chesster.io --redirect 2>&1
        
        CERTBOT_EXIT=$?
        
        if [ $CERTBOT_EXIT -eq 0 ]; then
            echo "$(date): SSL certificate installed successfully!"
            echo "$(date): HTTPS is now live at https://chesster.io"
            # Reload nginx to be sure
            systemctl reload nginx
            exit 0
        else
            echo "$(date): Certbot failed with exit code $CERTBOT_EXIT"
            echo "$(date): Will retry in 60 seconds..."
        fi
    else
        echo "$(date): Attempt $ATTEMPT/$MAX_ATTEMPTS - DNS not ready yet (got: '$RESULT')"
    fi
    
    sleep 60
done

echo "$(date): DNS did not propagate after $MAX_ATTEMPTS attempts. Giving up."
exit 1
