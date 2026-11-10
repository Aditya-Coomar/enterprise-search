// src/utils/jwt.ts
import jwt from 'jsonwebtoken';
import { config } from '../config/config';

if (!config.jwt.secret) {
  throw new Error('JWT_SECRET is missing in environment variables.');
}
const jwtSecret: jwt.Secret = config.jwt.secret;
const jwtExpiration = (config.jwt.expiration ||
  '1d') as jwt.SignOptions['expiresIn'];

const jwtIssuer = config.jwt.issuer || 'issuer_not_specified';
export function signToken(payload: object): string {
  return jwt.sign(payload, jwtSecret, {
    expiresIn: jwtExpiration,
    issuer: jwtIssuer,
  });
}

export function verifyToken<T = any>(token: string): T {
  return jwt.verify(token, jwtSecret) as T;
}
