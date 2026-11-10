import { Request } from 'express';

/**
 * Extracts the real client IP address from request headers and connection info.
 * Handles various proxy configurations including Docker, nginx, Cloudflare, etc.
 * 
 * @param req Express request object
 * @returns Object containing detected IP and debugging information
 */
export function extractClientIP(req: Request): {
  ip: string;
  source: string;
  headers: Record<string, string | undefined>;
  rawIP: string | undefined;
} {
  // Collect all relevant headers for debugging
  const headers = {
    'x-forwarded-for': req.get('X-Forwarded-For'),
    'x-real-ip': req.get('X-Real-IP'),
    'cf-connecting-ip': req.get('CF-Connecting-IP'),
    'x-client-ip': req.get('X-Client-IP'),
    'x-forwarded': req.get('X-Forwarded'),
    'forwarded-for': req.get('Forwarded-For'),
    'forwarded': req.get('Forwarded'),
  };

  const rawIP = req.ip;
  let detectedIP: string | undefined;
  let source = 'unknown';

  // Priority order for IP detection
  
  // 1. X-Forwarded-For (most common, can contain multiple IPs)
  if (headers['x-forwarded-for']) {
    const forwardedIPs = headers['x-forwarded-for'].split(',').map(ip => ip.trim());
    // Take the first IP (original client), not the last (immediate proxy)
    detectedIP = forwardedIPs[0];
    source = 'X-Forwarded-For';
  }
  
  // 2. X-Real-IP (nginx and other reverse proxies)
  else if (headers['x-real-ip']) {
    detectedIP = headers['x-real-ip'].trim();
    source = 'X-Real-IP';
  }
  
  // 3. CF-Connecting-IP (Cloudflare)
  else if (headers['cf-connecting-ip']) {
    detectedIP = headers['cf-connecting-ip'].trim();
    source = 'CF-Connecting-IP';
  }
  
  // 4. X-Client-IP (some proxies and load balancers)
  else if (headers['x-client-ip']) {
    detectedIP = headers['x-client-ip'].trim();
    source = 'X-Client-IP';
  }
  
  // 5. Express req.ip (when trust proxy is configured)
  else if (req.ip && req.ip !== '::1' && req.ip !== '127.0.0.1' && !req.ip.startsWith('::ffff:127.0.0.1')) {
    detectedIP = req.ip;
    source = 'req.ip';
  }
  
  // 6. Connection remote address (direct connection)
  else if (req.connection?.remoteAddress) {
    detectedIP = req.connection.remoteAddress;
    source = 'connection.remoteAddress';
  }
  
  // 7. Socket remote address (fallback)
  else if ((req as any).socket?.remoteAddress) {
    detectedIP = (req as any).socket.remoteAddress;
    source = 'socket.remoteAddress';
  }

  // Clean up the detected IP
  if (detectedIP) {
    // Remove IPv6 prefix for IPv4 addresses
    if (detectedIP.startsWith('::ffff:')) {
      detectedIP = detectedIP.substring(7);
    }
    
    // Validate IP format (basic check)
    if (!isValidIP(detectedIP)) {
      detectedIP = undefined;
      source = 'invalid-format';
    }
  }

  // Final fallback
  const finalIP = detectedIP || 'unknown';
  if (!detectedIP) {
    source = 'fallback-unknown';
  }

  return {
    ip: finalIP,
    source,
    headers,
    rawIP
  };
}

/**
 * Basic IP address validation
 * @param ip IP address to validate
 * @returns true if valid IPv4 or IPv6 address
 */
function isValidIP(ip: string): boolean {
  // IPv4 regex
  const ipv4Regex = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
  
  // IPv6 regex (simplified)
  const ipv6Regex = /^(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$|^::1$|^::$/;
  
  // Check for private/local addresses that might be proxy addresses
  const isPrivateIPv4 = /^(10\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.|127\.|169\.254\.)/.test(ip);
  
  if (ipv4Regex.test(ip)) {
    // Accept private IPs in development, but flag them
    return true;
  }
  
  if (ipv6Regex.test(ip)) {
    return true;
  }
  
  return false;
}

/**
 * Determines if an IP address is likely from a private network or localhost
 * @param ip IP address to check
 * @returns true if the IP is private/local
 */
export function isPrivateOrLocalIP(ip: string): boolean {
  if (!ip || ip === 'unknown') return false;
  
  // IPv4 private ranges
  const privateIPv4Patterns = [
    /^127\./, // Loopback
    /^10\./, // Private Class A
    /^172\.(1[6-9]|2[0-9]|3[01])\./, // Private Class B
    /^192\.168\./, // Private Class C
    /^169\.254\./, // Link-local
  ];
  
  // IPv6 private ranges
  const privateIPv6Patterns = [
    /^::1$/, // Loopback
    /^fe80:/, // Link-local
    /^fc00:/, // Unique local
    /^fd00:/, // Unique local
  ];
  
  return privateIPv4Patterns.some(pattern => pattern.test(ip)) || 
         privateIPv6Patterns.some(pattern => pattern.test(ip));
}
