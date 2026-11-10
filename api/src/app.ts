import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import rateLimit from 'express-rate-limit';
import { errorHandler } from './middlewares/errorHandler';
import logger from './utils/logger';
import { extractClientIP, isPrivateOrLocalIP } from './utils/ipUtils';
import HealthRoutes from './routes/health';
import SampleRoutes from './routes/sample-route';

const app = express();

// Configure Express to trust proxy headers
// This is essential for proper IP detection behind proxies, load balancers, Docker, etc.
app.set('trust proxy', 1); // Trust first proxy

// CORS configuration
app.use(
  cors({
    origin: function (origin, callback) {
      // Allow requests with no origin (like mobile apps, curl, postman)
      if (!origin) return callback(null, true);

      const allowedOrigins = [
        'http://localhost:3000',
        'http://localhost:3001',
        'http://localhost:3002',
        'http://localhost:8080',
        'http://127.0.0.1:3000',
        'http://127.0.0.1:8080',
        'null', // Allow null origin for local file testing
      ];

      // Check if origin is in allowed list or starts with localhost
      if (allowedOrigins.includes(origin) || origin?.includes('localhost')) {
        return callback(null, true);
      }

      return callback(null, true); // Allow all origins for development
    },
    credentials: true,
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    allowedHeaders: [
      'Content-Type',
      'Authorization',
      'Origin',
      'X-Requested-With',
      'Accept',
    ],
    optionsSuccessStatus: 200, // Some legacy browsers (IE11, various SmartTVs) choke on 204
  }),
);

// Security middleware
app.use(helmet());

// Rate limiting
const limiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 100, // limit each IP to 100 requests per windowMs
  message: {
    status: 'error',
    message: 'Too many requests from this IP, please try again later.',
  },
  standardHeaders: true,
  legacyHeaders: false,
});

app.use(limiter);

// Body parsing middleware
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

// Request logging with enhanced IP detection
app.use((req, res, next) => {
  const ipInfo = extractClientIP(req);
  const isPrivateIP = isPrivateOrLocalIP(ipInfo.ip);

  logger.info('Incoming request', {
    method: req.method,
    url: req.url,
    ip: ipInfo.ip,
    ipSource: ipInfo.source,
    isPrivateIP,
    userAgent: req.get('User-Agent'),
    // Include proxy headers for debugging in development
    ...(process.env.NODE_ENV !== 'production' && {
      rawIP: ipInfo.rawIP,
      proxyHeaders: ipInfo.headers,
    }),
  });

  // Add the detected IP info to the request object for use in other middleware/routes
  (req as any).clientIP = ipInfo;

  next();
});

// Routes
app.get('/', (req, res) => {
  const baseUrl = `${req.protocol}://${req.get('host')}`;
  res.json({
    message: 'Welcome to Your-APP-NAME API',
    status: 'success',
    version: '1.0.0',
    iss: 'Your-APP-NAME',
    timestamp: new Date().toISOString(),
  });
});

// Health check route
app.use('/api/health', HealthRoutes);
// Sample route
app.use('/api/sample', SampleRoutes);

// 404 handler
app.use((req, res) => {
  res.status(404).json({
    status: 'error',
    message: 'Route not found',
  });
});

// Global error handler (should be after routes)
app.use(errorHandler);

export default app;
