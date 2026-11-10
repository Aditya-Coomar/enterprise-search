import { Request, Response } from 'express';
import logger from '../utils/logger';

const sampleController = async (req: Request, res: Response) => {
  try {
    // Sample logic here
    res.status(200).json({ message: 'Sample controller response' });
  } catch (error) {
    logger.error('Sample controller error', { error });
    res.status(500).json({ message: 'Internal server error' });
  }
};

export { sampleController };
