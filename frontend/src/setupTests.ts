import { TextDecoder, TextEncoder } from "util";

// react-router v7 needs TextEncoder, which jsdom does not provide
Object.assign(global, { TextEncoder, TextDecoder });
