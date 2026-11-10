import { sampleController } from '../controllers/your-route-controllers';

import { Router } from 'express';
const router = Router();

router.get('/sample-endpoint', sampleController);

export default router;
