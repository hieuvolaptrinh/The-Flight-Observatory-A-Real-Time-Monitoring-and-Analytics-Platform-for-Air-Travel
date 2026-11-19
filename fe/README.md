# FlightLens — frontend kết nối backend

Frontend hiện dùng API thật. Trình duyệt gọi `/api/...` cùng origin; Next.js chuyển tiếp tới gateway bằng `API_GATEWAY_URL` (local mặc định `http://127.0.0.1:2002`, Docker dùng `http://gateway:8080`). Đặt `NEXT_PUBLIC_API_BASE_URL=/api` trong `.env.local` và khởi động lại frontend khi đổi cấu hình.

- `/analytics`: đọc kết quả đã lưu; **Chạy phân tích** tạo kết quả cho khoảng ngày được chọn.
- `/`: Tổng quan tự cập nhật 8 giây/lần, hiển thị lỗi API và giữ số liệu cũ khi mất kết nối.
- `/flights`: chuyển Raw/Đã xử lý, nhấn **So sánh** trên dòng raw, xem JSON đầy đủ và bảng thời tiết trước/sau đổi đơn vị.
- `/forecast`: đọc Prediction API; trạng thái thiếu model được hiển thị riêng, không dùng độ trễ quan sát làm dự báo thay thế.

Kiểm tra frontend: `npm run test:api`, `npx tsc --noEmit`, `npm run build`.

Hai màn hình cho phần việc của Hiếu:

- `/`: Tổng quan — KPI, tỷ lệ trễ theo giờ, tỷ trọng đúng giờ/trễ, top sân bay hoặc hãng bay, lần cập nhật.
- `/forecast`: Dự báo ngày mai — delay dự kiến, xác suất và nhãn nguy cơ, biểu đồ theo sân bay, bảng chi tiết.

## Chạy local

```powershell
cd D:\IT\Plant-Delay\fe
npm run dev
```

Mở http://localhost:3000 và http://localhost:3000/forecast.

## Ghi chú của phiên bản mẫu cũ

Các ghi chú dưới đây mô tả phiên bản mẫu cũ, không phải luồng API hiện tại.
Ngày tham chiếu cố định: 06/11/2026. Ngày dự báo: 07/11/2026.
Giờ cập nhật dùng UTC; giờ khởi hành trong bảng dự báo dùng giờ địa phương sân bay xuất phát.
Nút Làm mới tải lại dữ liệu mẫu và hiển thị thời điểm xem lại; không gọi inference hoặc training.
Các bộ lọc, tìm kiếm, sắp xếp, chuyển xếp hạng và xuất CSV hoạt động trong trình duyệt.
Bộ lọc sân bay ở trang dự báo áp dụng cho sân bay khởi hành.

Ngưỡng phân loại minh họa theo xác suất trễ từ 15 phút: thấp <30%, trung bình 30%–<60%, cao ≥60%.
KPI, biểu đồ dự báo áp dụng bộ lọc sân bay/hãng. Bộ lọc nguy cơ và tìm kiếm áp dụng riêng cho bảng chi tiết.
Số phút trễ dự kiến và xác suất trễ là hai đầu ra khác nhau của mô hình minh họa.
Để tích hợp, thay dữ liệu demo bằng response backend và thống nhất ngày dự báo, múi giờ, ngưỡng nhãn với nhóm Prediction/Classification.

## Cấu trúc

- `app/ui/dashboard.tsx`: giao diện dùng chung cho hai trang.
- `app/ui/demo-data.ts`: dữ liệu mẫu và quy tắc nhãn nguy cơ.
- `app/globals.css`: style và bố cục responsive, dùng CSS thuần, không cần tải font từ mạng.
- `app/page.tsx`, `app/forecast/page.tsx`: hai route.

Đã xác minh build production và TypeScript; kiểm tra trình duyệt ở desktop và chiều rộng 390px, lọc JFK, chuyển xếp hạng hãng bay, lọc/sắp xếp nguy cơ cao, trạng thái tìm kiếm rỗng và tải CSV.
Ảnh review được lưu tại `../outputs/ui-previews/`.
