import Print from 'vue-print-nb'
import VDistpicker from 'v-distpicker'

export default async ({ app, router, store, Vue }) => {
  Vue.component('v-distpicker', VDistpicker)
  Vue.use(Print)
  console.log('Welcome To 3Form WMS')
}
