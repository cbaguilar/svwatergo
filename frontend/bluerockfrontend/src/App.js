import './App.css';
import Todo from './counter/Todo';
import { store } from "./app/store"
import { Provider } from 'react-redux';
import React from 'react';

function App() {
  return (
    <AdminLTE title={["Hello", "World"]} titleShort={["He", "we"]} theme="blue" >

      <Provider store={store} path="/">
          <Todo />
      </Provider>
   </AdminLTE>
  );
}

export default App;
