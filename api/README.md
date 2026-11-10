# Express + TypeScript Backend Template

A secure, rate-limited REST API backend template built with Express and TypeScript. Includes enhanced logging, IP detection, and security best practices.

## Features

- Express.js with TypeScript
- Security headers via [helmet](https://www.npmjs.com/package/helmet)
- CORS enabled
- Rate limiting (100 requests per 15 minutes per IP)
- Enhanced request logging with IP detection
- Graceful shutdown handling
- Centralized error handling

## Getting Started

### Prerequisites

- Node.js (v18+ recommended)
- npm

### Installation

```bash
npm install
```

### Environment Variables

Create a `.env` file in the root directory. Example:

```
PORT=3000
NODE_ENV=development
```

### Development

Start the server with hot-reloading:

```bash
npm run dev
```

### Build

Compile TypeScript to JavaScript:

```bash
npm run build
```

### Production

Start the compiled server:

```bash
npm start
```

## License

See [LICENSE](LICENSE).
