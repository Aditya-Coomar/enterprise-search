import winston from 'winston';
import dotenv from 'dotenv';

// Load environment variables from .env file
dotenv.config();

// Get NODE_ENV from environment variables
const nodeEnv = process.env.NODE_ENV || 'development';

// Create base transports - console only (no file logging)
const transports: winston.transport[] = [
  new winston.transports.Console({
    format: winston.format.combine(
      winston.format.colorize(),
      winston.format.simple(),
    ),
  }),
];

const logger = winston.createLogger({
  level: nodeEnv === 'production' ? 'info' : 'debug',
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.errors({ stack: true }),
    winston.format.json(),
  ),
  defaultMeta: {
    service: 'reflow-admin-api',
    environment: nodeEnv,
  },
  transports,
});

// Log initialization information
logger.info('Logger initialized', {
  environment: nodeEnv,
  transportsCount: transports.length,
  logLevel: nodeEnv === 'production' ? 'info' : 'debug',
});

export default logger;
