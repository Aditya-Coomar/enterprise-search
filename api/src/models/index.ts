// src/models/index.ts

import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

// Export prisma instance for direct use if needed
export default prisma;
