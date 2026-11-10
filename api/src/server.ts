import app from './app';
import logger from './utils/logger';

const PORT = process.env.PORT || 3000;

// Initialize database connection and start server
async function startServer() {
  try {
    // Start the Express server
    const server = app.listen(PORT, () => {
      logger.info(`Server running on port ${PORT}`);
      console.log(`Server running on port ${PORT}`);
    });

    // Handle graceful shutdown
    const gracefulShutdown = async (signal: string) => {
      logger.info(`${signal} received, shutting down gracefully`);

      // Close server
      server.close(async () => {
        try {
          process.exit(0);
        } catch (error) {
          logger.error('Error during graceful shutdown:', error);
          process.exit(1);
        }
      });

      // Force close after 10 seconds
      setTimeout(() => {
        logger.error('Forced shutdown after timeout');
        process.exit(1);
      }, 10000);
    };

    process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));
    process.on('SIGINT', () => gracefulShutdown('SIGINT'));
  } catch (error) {
    logger.error('Failed to start server:', error);
    console.error('Failed to start server:', error);
    process.exit(1);
  }
}

// Start the server
startServer();
