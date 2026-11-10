import logger from '../utils/logger';
import { Router } from 'express';
import { PrismaClient } from '@prisma/client';
const router = Router();
const prisma = new PrismaClient();
import { config } from '../config/config';

router.get('/', async (req, res) => {
  const getDatabaseStatus = async () => {
    try {
      await prisma.$connect();
      return { status: 'ok', message: 'Database connection is healthy' };
    } catch (error) {
      logger.error('Database connection error', { error });
      return { status: 'error', message: 'Database connection failed' };
    }
  };

  try {
    const dbStatus = await getDatabaseStatus();
    res.status(dbStatus.status === 'ok' ? 200 : 503).json({
      status: 'success',
      message: 'Health check successful',
      database: dbStatus,
      version: '1.0.0',
      iss: config.jwt.issuer,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    logger.error('Health check error', { error });
    res.status(500).json({
      status: 'error',
      message: 'Health check failed',
      error: error instanceof Error ? error.message : String(error),
      version: '1.0.0',
      iss: config.jwt.issuer,
      timestamp: new Date().toISOString(),
    });
  }
});

export default router;
