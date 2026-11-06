# FlightLens — mẫu frontend

Hai màn hình cho phần việc của Hiếu:

- `/`: Tổng quan — KPI, tỷ lệ trễ theo giờ, tỷ trọng đúng giờ/trễ, top sân bay hoặc hãng bay, lần cập nhật.
- `/forecast`: Dự báo ngày mai — delay dự kiến, xác suất và nhãn nguy cơ, biểu đồ theo sân bay, bảng chi tiết.

## Chạy local

```powershell
cd D:\IT\Plant-Delay\fe
npm run dev
```

Mở http://localhost:3000 và http://localhost:3000/forecast.

## Phạm vi demo

Dữ liệu tổng hợp nằm ở `app/ui/demo-data.ts`, chưa gọi API hoặc chạy mô hình.
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
