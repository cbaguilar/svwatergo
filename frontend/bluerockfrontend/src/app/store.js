import { configureStore } from '@reduxjs/toolkit';
import cachesReducer from "../counter/CachesSlice";

export const store = configureStore({
    reducer: {
        caches: cachesReducer
    },
});
